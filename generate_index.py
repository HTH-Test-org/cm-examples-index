import os
import requests
import json
import base64
from datetime import datetime

# Configuration
ORG_NAME = os.environ.get("GITHUB_ORG", "HTH-Test-org")
TOKEN = os.environ.get("GITHUB_TOKEN")

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def get_org_repos():
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{ORG_NAME}/repos?type=public&per_page=100&page={page}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        page_data = response.json()
        if not page_data:
            break
        repos.extend(page_data)
        page += 1
    return repos

def get_meta_file(repo_name):
    url = f"https://api.github.com/repos/{ORG_NAME}/{repo_name}/contents/hcm-meta.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        content_b64 = response.json()['content']
        content_str = base64.b64decode(content_b64).decode('utf-8')
        try:
            return json.loads(content_str)
        except json.JSONDecodeError:
            print(f"  -> WARNING: Invalid JSON format in {repo_name}")
            return None
    return None

def get_repo_releases(repo_name):
    url = f"https://api.github.com/repos/{ORG_NAME}/{repo_name}/releases"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return []

def get_zip_size(url):
    """Downloads the file in memory stream to calculate exact byte size."""
    try:
        response = requests.get(url, headers=HEADERS, stream=True)
        if 'Content-Length' in response.headers:
            return int(response.headers['Content-Length'])
        
        size = 0
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                size += len(chunk)
        return size
    except Exception as e:
        print(f"  -> Warning: Could not calculate size for {url} ({e})")
        return 0

def main():
    print(f"Starting catalog generation for organization: {ORG_NAME}")
    if not TOKEN:
        raise ValueError("GITHUB_TOKEN environment variable is missing!")
        
    repos = get_org_repos()
    print(f"Found {len(repos)} repositories. Scanning for metadata...")
    
    catalog = []

    for repo in repos:
        repo_name = repo['name']
        meta = get_meta_file(repo_name)
        if not meta:
            continue
            
        print(f"Processing repository: {repo_name}")
        releases = get_repo_releases(repo_name)
        versions_list = []
        
        for index, rel in enumerate(releases):
            pub_date = datetime.strptime(rel['published_at'], "%Y-%m-%dT%H:%M:%SZ")
            epoch_ms = int(pub_date.timestamp() * 1000)
            
            zip_url = rel['zipball_url']
            print(f"  -> Calculating size for version {rel['tag_name']}...")
            calculated_size = get_zip_size(zip_url)
            
            versions_list.append({
                "version": rel['tag_name'],
                "isLatest": (index == 0),
                "downloadUrl": zip_url,
                "releaseNotes": rel.get('body', ''),
                "sizeBytes": calculated_size,
                "lastModifiedEpoch": epoch_ms
            })
            
        if not versions_list:
            print(f"  -> No releases found for {repo_name}. Skipping repository.")
            continue

        # 3. Assemble the final entry format expected by the Java Content Manager
        entry = {
            "id": repo_name,
            "displayName": meta.get("displayName", repo_name),
            "abstract": meta.get("abstract", ""),
            "device": meta.get("device", ""),
            "tags": meta.get("tags", []),
            "contentType": meta.get("contentType", "ECLIPSE_GENPRJ_STD"),
            "githubInfo": {                                            
                "repoUrl": f"https://github.com/{ORG_NAME}/{repo_name}"
            },                                                         
            "versions": versions_list
        }
        catalog.append(entry)

    # 4. Write the JSON array to a file
    output_filename = "examples.json"
    
    final_output = {
        "examples": catalog
    }
    
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)
        
    print(f"Success! {len(catalog)} examples written to {output_filename}")

if __name__ == "__main__":
    main()