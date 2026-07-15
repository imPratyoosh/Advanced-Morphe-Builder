import os
import re
import sys

# We use tomllib to read your config.toml and map patches to their owners!
try:
    import tomllib
except ImportError:
    print("Error: Python 3.11+ is required. Please update python-version to '3.11' in your workflow.")
    sys.exit(1)

LOG_FILE = 'build.log'
TEMPLATE_FILE = 'README.template.md'
OUTPUT_FILE = 'README.md'
CONFIG_FILE = 'config.toml'

# Load your config file to act as a map for multi-bundle apps
config_data = {}
try:
    with open(CONFIG_FILE, 'rb') as f:
        config_data = tomllib.load(f)
except FileNotFoundError:
    print(f"Warning: {CONFIG_FILE} not found. Multi-bundle tagging may fallback to primary bundle.")

apps_data = {}
current_app = None
current_bundles = []

def clean_terminal_formatting(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    text = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+', '', text)
    return text.strip()

def get_patch_repo(patch_name, app_name, config, bundles):
    """Maps a patch to its source bundle using your config.toml rules."""
    if config and app_name in config and 'patches' in config[app_name]:
        for source, details in config[app_name]['patches'].items():
            # Clean up the "github:" prefix
            clean_source = source.replace('github:', '').replace('gitlab:', '')
            if isinstance(details, dict):
                if patch_name in details.get('include', []) or patch_name in details.get('exclude', []):
                    return clean_source
            elif isinstance(details, list):
                if patch_name in details:
                    return clean_source
                    
    # If not explicitly included in config (like a default patch), assume primary bundle
    if len(bundles) >= 1:
        return bundles[0]['repo']
    return "Unknown Bundle"

# 1. Parse the log file line by line
try:
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            clean_line = clean_terminal_formatting(line)
            
            # Reset trackers for the next app when a build finishes
            if "[+] Built" in clean_line or "[+] Done" in clean_line:
                current_bundles = []
                current_app = None

            # Detect Patch Bundles (e.g., [+] Getting 'patches-1.34.0.mpp' from ...)
            elif "Getting '" in clean_line and "' from '" in clean_line:
                match = re.search(r"Getting '(.*?)' from '(.*?)'", clean_line)
                if match:
                    filename = match.group(1)
                    url = match.group(2)
                    
                    # Ignore the cli jar, we only want the patch bundles
                    if "cli" not in filename.lower() and "jar" not in filename.lower():
                        # Extract Owner/Repo from URL
                        repo_match = re.search(r'/repos/([^/]+/[^/]+)', url)
                        repo = repo_match.group(1) if repo_match else "Unknown/Repo"
                        
                        # Extract version (e.g. patches-1.34.0.mpp -> 1.34.0)
                        v_match = re.search(r'([\d\.]+)', filename)
                        version = v_match.group(1) if v_match else filename.replace('.mpp', '').replace('patches-', '')
                        
                        # Avoid duplicates
                        if not any(b['repo'] == repo for b in current_bundles):
                            current_bundles.append({'repo': repo, 'version': version})

            # Catch app name early
            elif "[+] Package name of '" in clean_line:
                match = re.search(r"Package name of '(.*?)' is", clean_line)
                if match:
                    current_app = match.group(1)
                    if current_app not in apps_data:
                        apps_data[current_app] = {'version': "Unknown", 'bundles': current_bundles.copy(), 'applied': [], 'excluded': []}
                        
            # Detect App Name & Exact App Version
            elif "[+] Choosing version '" in clean_line:
                match = re.search(r"Choosing version '(.*?)' for '(.*?)'", clean_line)
                if match:
                    current_app = match.group(2)
                    if current_app not in apps_data:
                        apps_data[current_app] = {'version': match.group(1), 'bundles': current_bundles.copy(), 'applied': [], 'excluded': []}
                    else:
                        apps_data[current_app]['version'] = match.group(1)
                        if not apps_data[current_app]['bundles']:
                            apps_data[current_app]['bundles'] = current_bundles.copy()
                            
            # Detect Applied Patches
            elif current_app and "INFO: Applied: " in clean_line:
                patch = clean_line.split("INFO: Applied: ")[1].strip()
                if patch not in apps_data[current_app]['applied']:
                    apps_data[current_app]['applied'].append(patch)
                    
            # Detect Manually Excluded Patches
            elif current_app and "INFO: Skipping disabled: " in clean_line:
                patch = clean_line.split("INFO: Skipping disabled: ")[1].strip()
                if not patch.endswith("(default)"):
                    if patch not in apps_data[current_app]['excluded']:
                        apps_data[current_app]['excluded'].append(patch)

except FileNotFoundError:
    print(f"Error: {LOG_FILE} not found.")
    sys.exit(1)

# 2. Format the parsed data into Markdown
apps_md = ""
for index, (app_name, data) in enumerate(apps_data.items(), start=1):
    applied = data['applied']
    excluded = data['excluded']
    bundles = data['bundles']
    
    # Extract lists of repos and versions
    repos_list = [b['repo'] for b in bundles]
    versions_list = [b['version'] for b in bundles]
    
    apps_md += f"<details>\n<summary><b>{index}. {app_name}</b></summary>\n\n"
    
    # Add Versions and Bundles
    apps_md += f"* **App Version:** `{data['version']}`\n"
    if repos_list:
        apps_md += f"* **Patch Bundles:** `{', '.join(repos_list)}`\n"
    if versions_list:
        apps_md += f"* **Patches Version:** `{', '.join(versions_list)}`\n"
        
    apps_md += "\n"
    
    # Add Applied Patches
    apps_md += f"* **Applied Patches ({len(applied)}):**\n"
    if applied:
        for patch in sorted(applied):
            # Only append the (Owner/repo) tag if the app actually uses more than 1 bundle!
            repo = get_patch_repo(patch, app_name, config_data, bundles)
            tag = f" *({repo})*" if repo and len(bundles) > 1 else ""
            apps_md += f"  * `{patch}`{tag}\n"
    else:
        apps_md += "  * `No patches detected.`\n"
        
    # Add Excluded Patches
    if excluded:
        apps_md += f"\n* **Excluded Patches ({len(excluded)}):**\n"
        for patch in sorted(excluded):
            repo = get_patch_repo(patch, app_name, config_data, bundles)
            tag = f" *({repo})*" if repo and len(bundles) > 1 else ""
            apps_md += f"  * `{patch}`{tag}\n"
            
    apps_md += "</details>\n\n"

# 3. Inject into README template
try:
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        template = f.read()
except FileNotFoundError:
    print(f"Error: {TEMPLATE_FILE} not found.")
    sys.exit(1)

final_readme = template.replace('{{APPS_LIST}}', apps_md.strip())

# 4. Save the final README
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(final_readme)

print("README.md successfully updated with full version and patch tracking!")
