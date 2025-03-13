#!/usr/bin/env python3
"""
Stash Studio Match Scrape

A Python script for matching studios in your Stash database with ThePornDB and StashDB.
This tool helps you automatically update your studio metadata with information from these external databases.

GitHub: https://github.com/yourusername/stashStudioMatchScrape
License: MIT
"""

import requests
import stashapi.log as log
from datetime import datetime, timedelta
import time
import json
import sys
import os
import select
import argparse
import importlib.util

# Try to import the user's config file, fall back to template if not available
try:
    # First try to import the user's config
    if os.path.exists('config.py'):
        spec = importlib.util.spec_from_file_location("config", "config.py")
        if spec is not None and spec.loader is not None:
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            config = config_module.config
            print("Using configuration from config.py")
        else:
            raise ImportError("Could not load config.py")
    else:
        # Fall back to template config
        from config_template import config
        print("Using configuration from config_template.py")
        print("WARNING: You are using template configuration. Please copy config_template.py to config.py and update with your credentials.")
except ImportError:
    # If neither exists, define a default config
    config = {
        'scheme': 'http',
        'host': 'localhost',
        'port': 9999,
        'api_key': '',
        'tpdb_api_key': '',
        'stashdb_api_key': '',
        'log_file': 'studio_match_progress.log',
    }
    print("WARNING: No configuration found. Using default values. Please create a config.py file with your credentials.")

# Build API URLs
local_api_url = f"{config['scheme']}://{config['host']}:{config['port']}/graphql"
tpdb_api_url = "https://theporndb.net/graphql"
tpdb_rest_api_url = "https://api.theporndb.net"
stashdb_api_url = "https://stashdb.org/graphql"

# Set up logging to file
def setup_logging():
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(log_dir, config['log_file'])
    
    # Create a custom logger function that writes to both stashapi.log and our file
    def custom_log(message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        
        # Write to our custom log file
        with open(log_path, "a") as f:
            f.write(log_message + "\n")
        
        # Also print to console when running from command line
        print(log_message)
        
        # Also use the stashapi logging
        if level == "INFO":
            log.info(message)
        elif level == "ERROR":
            log.error(message)
        elif level == "DEBUG":
            log.debug(message)
        elif level == "PROGRESS":
            log.progress(float(message))
    
    return custom_log

# Initialize logger
logger = setup_logging()

# GraphQL queries and mutations
local_find_studio_query = """
query FindLocalStudio($id: ID!) {
    findStudio(id: $id) {
        id
        name
        url
        parent_studio {
            id
            name
        }
        stash_ids {
            endpoint
            stash_id
        }
    }
}
"""

all_studios_query = """
query AllStudios {
    allStudios {
        id
        name
        url
        parent_studio {
            id
            name
        }
        stash_ids {
            endpoint
            stash_id
        }
    }
}
"""

# Updated search queries for ThePornDB and StashDB
# ThePornDB uses searchSite instead of searchStudio
search_site_query_tpdb = """
query SearchSite($term: String!) {
    searchSite(term: $term) {
        id
        name
    }
}
"""

# StashDB query remains the same
search_studio_query_stashdb = """
query SearchStudio($term: String!) {
    searchStudio(term: $term) {
        id
        name
    }
}
"""

# Updated find queries for ThePornDB and StashDB
find_site_query_tpdb = """
query FindStudio($id: ID!) {
    findStudio(id: $id) {
        id
        name
        url
        parent {
            id
            name
        }
        images {
            url
        }
    }
}
"""

# Updated StashDB query to match their API schema
find_studio_query_stashdb = """
query FindStudio($id: ID!) {
    findStudio(id: $id) {
        id
        name
        urls {
            url
            type
        }
        parent {
            id
            name
        }
        images {
            url
        }
    }
}
"""

studio_update_mutation = """
mutation StudioUpdate($input: StudioUpdateInput!) {
    studioUpdate(input: $input) {
        id
        name
        parent_studio {
            id
            name
        }
    }
}
"""

# Functions
def graphql_request(query, variables, endpoint, api_key, retries=5):
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Apikey'] = api_key
    for attempt in range(retries):
        try:
            logger(f"Making GraphQL request to {endpoint}", "DEBUG")
            response = requests.post(endpoint, json={'query': query, 'variables': variables}, headers=headers)
            response.raise_for_status()
            response_json = response.json()
            if 'errors' in response_json:
                logger(f"GraphQL request returned errors: {response_json['errors']}", "ERROR")
                return None
            return response_json.get('data')
        except requests.exceptions.RequestException as e:
            logger(f"GraphQL request failed (attempt {attempt + 1} of {retries}): {e}", "ERROR")
            if attempt < retries - 1:
                sleep_time = 2 ** attempt
                logger(f"Retrying in {sleep_time} seconds...", "INFO")
                time.sleep(sleep_time)
            else:
                logger("Max retries reached. Giving up.", "ERROR")
                raise

def find_local_studio(studio_id):
    logger(f"Finding local studio with ID: {studio_id}", "INFO")
    response = graphql_request(local_find_studio_query, {'id': studio_id}, local_api_url, config['api_key'])
    if response:
        return response.get('findStudio')
    return None

def get_all_studios():
    logger("Getting all studios from local database", "INFO")
    response = graphql_request(all_studios_query, {}, local_api_url, config['api_key'])
    if response:
        studios = response.get('allStudios')
        logger(f"Found {len(studios)} studios in local database", "INFO")
        return studios
    return []

def search_studio(term, api_url, api_key):
    logger(f"Searching for studio '{term}' on {api_url}", "INFO")
    
    # Use different queries for different APIs
    if "theporndb.net" in api_url:
        # ThePornDB now uses a REST API for sites
        return search_tpdb_site(term, api_key)
    else:
        query = search_studio_query_stashdb
        response = graphql_request(query, {'term': term}, api_url, api_key)
        if response:
            results = response.get('searchStudio', [])
            logger(f"Found {len(results)} results for '{term}' on {api_url}", "INFO")
            return results
    
    return []

def search_tpdb_site(term, api_key):
    """Search for a site on ThePornDB using the REST API"""
    logger(f"Searching for site '{term}' on ThePornDB REST API", "INFO")
    
    url = f"{tpdb_rest_api_url}/sites"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }
    params = {
        'q': term
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'data' in data:
            sites = data['data']
            logger(f"Found {len(sites)} results for '{term}' on ThePornDB REST API", "INFO")
            
            # Convert to the same format as our GraphQL results
            results = []
            for site in sites:
                results.append({
                    'id': str(site.get('id')),
                    'name': site.get('name')
                })
            return results
        return []
    except requests.exceptions.RequestException as e:
        logger(f"ThePornDB REST API request failed: {e}", "ERROR")
        return []

def find_studio(studio_id, api_url, api_key):
    logger(f"Finding studio with ID {studio_id} on {api_url}", "INFO")
    
    # Use different queries for different APIs
    if "theporndb.net" in api_url:
        # ThePornDB now uses a REST API for sites
        return find_tpdb_site(studio_id, api_key)
    else:
        query = find_studio_query_stashdb
    
    try:
        response = graphql_request(query, {'id': studio_id}, api_url, api_key)
        
        if response:
            return response.get('findStudio')
        return None
    except Exception as e:
        logger(f"Error finding studio: {e}", "ERROR")
        # If we can't get detailed info, return basic info so we can at least add the stash_id
        return {
            'id': studio_id,
            'name': None,
            'urls': [],
            'images': [],
            'parent': None
        }

def find_tpdb_site(site_id, api_key):
    """Find a site on ThePornDB using the REST API"""
    logger(f"Finding site with ID {site_id} on ThePornDB REST API", "INFO")
    
    url = f"{tpdb_rest_api_url}/sites/{site_id}"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        response_data = response.json()
        
        # The API returns data wrapped in a 'data' object
        if 'data' in response_data:
            site = response_data['data']
            logger(f"Retrieved raw site data from ThePornDB REST API: {site}", "INFO")
            
            # Convert to the same format as our GraphQL results
            parent = None
            if site.get('parent_id'):
                # Try to get parent site info
                try:
                    parent_response = requests.get(f"{tpdb_rest_api_url}/sites/{site.get('parent_id')}", headers=headers)
                    parent_response.raise_for_status()
                    parent_data = parent_response.json()
                    if 'data' in parent_data:
                        parent_site = parent_data['data']
                        parent = {
                            'id': str(parent_site.get('id')),
                            'name': parent_site.get('name')
                        }
                except Exception as e:
                    logger(f"Error retrieving parent site: {e}", "ERROR")
                    # If we can't get parent info, just use the ID
                    parent = {
                        'id': str(site.get('parent_id')),
                        'name': None
                    }
            # Check for network as an alternative to parent
            elif site.get('network') and site.get('network').get('id'):
                network = site.get('network')
                parent = {
                    'id': str(network.get('id')),
                    'name': network.get('name')
                }
            
            # Build the result in the same format as StashDB
            result = {
                'id': str(site.get('id')),
                'name': site.get('name'),
                'urls': [],
                'parent': parent,
                'images': []
            }
            
            # Add URL if available
            if site.get('url'):
                result['urls'].append({
                    'url': site.get('url'),
                    'type': 'HOME'
                })
            
            # Add image if available
            if site.get('poster'):
                result['images'].append({
                    'url': site.get('poster')
                })
            elif site.get('logo'):
                result['images'].append({
                    'url': site.get('logo')
                })
            
            logger(f"Processed site data from ThePornDB REST API: {result}", "INFO")
            return result
        
        logger(f"No data found in ThePornDB REST API response for site ID {site_id}", "ERROR")
        return None
    except requests.exceptions.RequestException as e:
        logger(f"ThePornDB REST API request failed: {e}", "ERROR")
        return None

def find_or_create_parent_studio(parent_data, api_url):
    """Find a parent studio in the local database or create it if it doesn't exist"""
    if not parent_data:
        return None
    
    parent_id = parent_data.get('id')
    parent_name = parent_data.get('name')
    
    if not parent_id or not parent_name:
        return None
    
    logger(f"Looking for parent studio: {parent_name} (ID: {parent_id} on {api_url})", "INFO")
    
    # Try to find the studio by name first - use a direct query instead of a filter
    try:
        # Get all studios and filter in Python
        all_studios_query = """
        query AllStudios {
            allStudios {
                id
                name
                stash_ids {
                    endpoint
                    stash_id
                }
            }
        }
        """
        
        response = graphql_request(all_studios_query, {}, local_api_url, config['api_key'])
        
        if response and response.get('allStudios'):
            studios = response.get('allStudios')
            
            # First, check if any studio has the StashDB ID
            for studio in studios:
                if studio.get('stash_ids'):
                    for stash_id in studio['stash_ids']:
                        if stash_id.get('endpoint') == api_url and stash_id.get('stash_id') == parent_id:
                            logger(f"Found parent studio by StashDB ID: {studio['name']} (ID: {studio['id']})", "INFO")
                            return studio['id']
            
            # If not found by StashDB ID, look for exact match by name
            for studio in studios:
                if studio['name'].lower() == parent_name.lower():
                    logger(f"Found parent studio by name: {studio['name']} (ID: {studio['id']})", "INFO")
                    
                    # Add the stash_id to the parent studio
                    update_mutation = """
                    mutation UpdateStudio($input: StudioUpdateInput!) {
                        studioUpdate(input: $input) {
                            id
                            name
                        }
                    }
                    """
                    
                    variables = {
                        'input': {
                            'id': studio['id'],
                            'stash_ids': [{
                                'stash_id': parent_id,
                                'endpoint': api_url
                            }]
                        }
                    }
                    
                    try:
                        graphql_request(update_mutation, variables, local_api_url, config['api_key'])
                        logger(f"Added stash_id to parent studio: {studio['name']} (ID: {studio['id']})", "INFO")
                    except Exception as e:
                        logger(f"Error adding stash_id to parent studio: {e}", "ERROR")
                    
                    return studio['id']
        
        # If not found, create the parent studio
        create_mutation = """
        mutation CreateStudio($input: StudioCreateInput!) {
            studioCreate(input: $input) {
                id
                name
            }
        }
        """
        
        variables = {
            'input': {
                'name': parent_name,
                'stash_ids': [{
                    'stash_id': parent_id,
                    'endpoint': api_url
                }]
            }
        }
        
        try:
            response = graphql_request(create_mutation, variables, local_api_url, config['api_key'])
            
            if response and response.get('studioCreate'):
                parent_studio = response['studioCreate']
                logger(f"Created parent studio: {parent_studio['name']} (ID: {parent_studio['id']})", "INFO")
                return parent_studio['id']
        except Exception as e:
            logger(f"Error creating parent studio: {e}", "ERROR")
        
        logger(f"Failed to create parent studio: {parent_name}", "ERROR")
        return None
    except Exception as e:
        logger(f"Error finding or creating parent studio: {e}", "ERROR")
        return None

def update_studio(studio_data, local_id):
    logger(f"Updating studio with ID: {local_id}", "INFO")
    studio_data['id'] = local_id
    variables = {'input': studio_data}

    response = graphql_request(studio_update_mutation, variables, local_api_url, config['api_key'])
    if response:
        return response.get('studioUpdate')
    return None

def update_studio_data(studio):
    logger(f"Processing studio: {studio['name']} (ID: {studio['id']})", "INFO")

    # Check if the studio already has a TPDB or stashDB stash ID
    tpdb_id = None
    stashdb_id = None
    
    # Extract existing IDs if present
    for stash in studio['stash_ids']:
        if stash['endpoint'] == 'https://theporndb.net/graphql':
            tpdb_id = stash['stash_id']
        elif stash['endpoint'] == 'https://stashdb.org/graphql':
            stashdb_id = stash['stash_id']
    
    has_tpdb_id = tpdb_id is not None
    has_stashdb_id = stashdb_id is not None
    
    # Check if the studio already has a parent studio
    has_parent = studio.get('parent_studio') is not None
    
    logger(f"Studio {studio['name']} has TPDB ID: {has_tpdb_id} ({tpdb_id}), StashDB ID: {has_stashdb_id} ({stashdb_id}), Parent: {has_parent}", "INFO")

    # Search for matches on both ThePornDB and StashDB
    tpdb_match = None
    stashdb_match = None
    
    # Only search ThePornDB if we don't have a TPDB ID
    if not has_tpdb_id:
        tpdb_results = search_studio(studio['name'], tpdb_api_url, config['tpdb_api_key'])
        if tpdb_results:
            exact_matches = [result for result in tpdb_results if result['name'].lower() == studio['name'].lower()]

            if len(exact_matches) == 1:
                tpdb_match = exact_matches[0]
                logger(f"Found exact match on ThePornDB: {tpdb_match['name']} (ID: {tpdb_match['id']})", "INFO")
            elif len(exact_matches) > 1:
                logger(f"Skipped studio {studio['name']} due to multiple exact matches on ThePornDB.", "INFO")
            else:
                logger(f"No exact match found on ThePornDB for: {studio['name']}", "INFO")
    
    # Search for the studio on StashDB
    if not has_stashdb_id:
        stashdb_results = search_studio(studio['name'], stashdb_api_url, config['stashdb_api_key'])
        if stashdb_results:
            exact_matches = [result for result in stashdb_results if result['name'].lower() == studio['name'].lower()]

            if len(exact_matches) == 1:
                stashdb_match = exact_matches[0]
                logger(f"Found exact match on StashDB: {stashdb_match['name']} (ID: {stashdb_match['id']})", "INFO")
            elif len(exact_matches) > 1:
                logger(f"Skipped studio {studio['name']} due to multiple exact matches on stashDB.", "INFO")
            else:
                logger(f"No exact match found on stashDB for: {studio['name']}", "INFO")
    
    # Get studio data from both APIs if we have matches or existing IDs
    tpdb_studio_data = None
    stashdb_studio_data = None
    
    # Get ThePornDB data if we have a match or an existing ID
    if tpdb_match:
        tpdb_studio_data = find_studio(tpdb_match['id'], tpdb_api_url, config['tpdb_api_key'])
        logger(f"Retrieved ThePornDB data using matched ID: {tpdb_match['id']}", "INFO")
    elif tpdb_id:
        # If we already have a ThePornDB ID but no match (because we didn't search), get the data directly
        tpdb_studio_data = find_studio(tpdb_id, tpdb_api_url, config['tpdb_api_key'])
        if tpdb_studio_data:
            logger(f"Retrieved ThePornDB data using existing ID: {tpdb_id}", "INFO")
    
    # Get StashDB data if we have a match or an existing ID
    if stashdb_match:
        stashdb_studio_data = find_studio(stashdb_match['id'], stashdb_api_url, config['stashdb_api_key'])
        logger(f"Retrieved StashDB data using matched ID: {stashdb_match['id']}", "INFO")
    elif stashdb_id:
        # If we already have a StashDB ID but no match (because we didn't search), get the data directly
        stashdb_studio_data = find_studio(stashdb_id, stashdb_api_url, config['stashdb_api_key'])
        if stashdb_studio_data:
            logger(f"Retrieved StashDB data using existing ID: {stashdb_id}", "INFO")

    # Check if we need to update anything (new IDs or parent studio)
    need_update = (tpdb_match and not has_tpdb_id) or (stashdb_match and not has_stashdb_id) or (not has_parent and ((tpdb_studio_data and 'parent' in tpdb_studio_data and tpdb_studio_data['parent']) or (stashdb_studio_data and 'parent' in stashdb_studio_data and stashdb_studio_data['parent'])))
    
    if need_update or (stashdb_studio_data and 'parent' in stashdb_studio_data and stashdb_studio_data['parent']) or (tpdb_studio_data and 'parent' in tpdb_studio_data and tpdb_studio_data['parent']):
        # Combine data from both sources, with StashDB taking precedence
        combined_data = {}
        if tpdb_studio_data:
            combined_data.update(tpdb_studio_data)
            logger(f"Got studio data from ThePornDB: {tpdb_studio_data}", "INFO")
        if stashdb_studio_data:
            combined_data.update(stashdb_studio_data)
            logger(f"Got studio data from StashDB: {stashdb_studio_data}", "INFO")

        # Extract image URL, prioritizing StashDB
        image_url = None
        if stashdb_studio_data and isinstance(stashdb_studio_data, dict) and 'images' in stashdb_studio_data and stashdb_studio_data['images']:
            image_url = stashdb_studio_data['images'][0].get('url')
        elif tpdb_studio_data and isinstance(tpdb_studio_data, dict) and 'images' in tpdb_studio_data and tpdb_studio_data['images']:
            image_url = tpdb_studio_data['images'][0].get('url')

        # Extract URL, prioritizing StashDB
        url = None
        if stashdb_studio_data and isinstance(stashdb_studio_data, dict) and 'urls' in stashdb_studio_data and stashdb_studio_data['urls']:
            # Find the HOME type URL if available
            for url_obj in stashdb_studio_data['urls']:
                if url_obj.get('type') == 'HOME':
                    url = url_obj.get('url')
                    break
            # If no HOME type, just use the first URL
            if not url and stashdb_studio_data['urls']:
                url = stashdb_studio_data['urls'][0].get('url')
        elif tpdb_studio_data and isinstance(tpdb_studio_data, dict) and 'urls' in tpdb_studio_data and tpdb_studio_data['urls']:
            # Find the HOME type URL if available
            for url_obj in tpdb_studio_data['urls']:
                if url_obj.get('type') == 'HOME':
                    url = url_obj.get('url')
                    break
            # If no HOME type, just use the first URL
            if not url and tpdb_studio_data['urls']:
                url = tpdb_studio_data['urls'][0].get('url')

        # Handle parent studio, prioritizing StashDB
        parent_id = None
        if stashdb_studio_data and 'parent' in stashdb_studio_data and stashdb_studio_data['parent']:
            parent_id = find_or_create_parent_studio(stashdb_studio_data['parent'], stashdb_api_url)
            if parent_id:
                logger(f"Found parent studio ID from StashDB: {parent_id} for studio: {studio['name']}", "INFO")
        elif tpdb_studio_data and 'parent' in tpdb_studio_data and tpdb_studio_data['parent']:
            parent_id = find_or_create_parent_studio(tpdb_studio_data['parent'], tpdb_api_url)
            if parent_id:
                logger(f"Found parent studio ID from ThePornDB: {parent_id} for studio: {studio['name']}", "INFO")

        # Build the new stash_ids list
        new_stash_ids = []
        
        # Add existing stash IDs that are still valid
        for stash in studio['stash_ids']:
            if stash['endpoint'] == 'https://stashdb.org/graphql' and stashdb_match and stash['stash_id'] != stashdb_match['id']:
                # Skip invalid StashDB ID, we'll add the correct one below
                continue
            elif stash['endpoint'] == 'https://theporndb.net/graphql' and tpdb_match and stash['stash_id'] != tpdb_match['id']:
                # Skip invalid ThePornDB ID, we'll add the correct one below
                continue
            else:
                # Keep other IDs
                new_stash_ids.append(stash)
        
        # Add new ThePornDB ID if needed
        if tpdb_match and not any(s['endpoint'] == 'https://theporndb.net/graphql' and s['stash_id'] == tpdb_match['id'] for s in new_stash_ids):
            new_stash_ids.append({
                'stash_id': tpdb_match['id'],
                'endpoint': "https://theporndb.net/graphql"
            })
            logger(f"Adding ThePornDB ID: {tpdb_match['id']}", "INFO")
        
        # Add new StashDB ID if needed
        if stashdb_match and not any(s['endpoint'] == 'https://stashdb.org/graphql' and s['stash_id'] == stashdb_match['id'] for s in new_stash_ids):
            new_stash_ids.append({
                'stash_id': stashdb_match['id'],
                'endpoint': "https://stashdb.org/graphql"
            })
            logger(f"Adding StashDB ID: {stashdb_match['id']}", "INFO")

        # Only include fields that need to be updated
        studio_update_data = {
            'id': studio['id']  # Always include the ID
        }
        
        # Only add fields that have values and need to be updated
        if combined_data.get('name'):
            studio_update_data['name'] = combined_data.get('name')
        if url:
            studio_update_data['url'] = url
        if image_url:
            studio_update_data['image'] = image_url
        if new_stash_ids:
            studio_update_data['stash_ids'] = new_stash_ids
        if parent_id:
            studio_update_data['parent_id'] = parent_id

        # Only update if we have something to update
        if len(studio_update_data) > 1:  # More than just the ID
            logger(f"Prepared studio update data: {studio_update_data}", "INFO")

            try:
                update_result = update_studio(studio_update_data, studio['id'])
                if update_result:
                    logger(f"Updated studio: {update_result['name']} (ID: {update_result['id']}) with new data.", "INFO")
                    if update_result.get('parent_studio'):
                        logger(f"Set parent studio: {update_result['parent_studio']['name']} (ID: {update_result['parent_studio']['id']})", "INFO")
                else:
                    logger(f"No new details added for studio {studio['name']} (ID: {studio['id']}) - already up to date.", "INFO")
            except requests.exceptions.HTTPError as e:
                logger(f"Failed to update studio: {studio['name']} (ID: {studio['id']})", "ERROR")
                logger(str(e), "ERROR")
        else:
            logger(f"No new details to update for studio {studio['name']} (ID: {studio['id']})", "INFO")
    else:
        logger(f"No new details needed for studio {studio['name']} (ID: {studio['id']}) - already up to date.", "INFO")

def update_all_studios():
    studios = get_all_studios()
    
    # Check if we have a limit set
    args = parse_args()
    if args.limit and args.limit > 0 and args.limit < len(studios):
        logger(f"Limiting to first {args.limit} studios", "INFO")
        studios = studios[:args.limit]
    
    total_studios = len(studios)
    processed_count = 0
    start_time = time.time()
    
    logger(f"Starting batch update of {total_studios} studios at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")

    for studio in studios:
        update_studio_data(studio)

        # Update progress for each studio
        processed_count += 1
        progress_percentage = processed_count / total_studios
        
        # Calculate ETA
        elapsed_time = time.time() - start_time
        if processed_count > 0:
            avg_time_per_studio = elapsed_time / processed_count
            remaining_studios = total_studios - processed_count
            eta_seconds = avg_time_per_studio * remaining_studios
            eta_str = str(timedelta(seconds=int(eta_seconds)))
        else:
            eta_str = "Unknown"
        
        # Log progress
        logger(progress_percentage, "PROGRESS")
        logger(f"Processed {processed_count}/{total_studios} studios ({progress_percentage*100:.2f}%) - ETA: {eta_str}", "INFO")

    # Log completion
    total_time = time.time() - start_time
    logger(f"Completed batch update of {total_studios} studios in {str(timedelta(seconds=int(total_time)))}", "INFO")

def update_single_studio(studio_id):
    studio = find_local_studio(studio_id)
    if studio:
        update_studio_data(studio)
    else:
        logger(f"Studio with ID {studio_id} not found.", "ERROR")

def find_studio_by_name(name):
    logger(f"Searching for studio with name: {name}", "INFO")
    studios = get_all_studios()
    
    # Look for exact match first
    for studio in studios:
        if studio['name'].lower() == name.lower():
            logger(f"Found exact match for studio name: {name} (ID: {studio['id']})", "INFO")
            return studio
    
    # If no exact match, look for partial matches
    matches = []
    for studio in studios:
        if name.lower() in studio['name'].lower():
            matches.append(studio)
    
    if len(matches) == 1:
        logger(f"Found one partial match for studio name: {name} (ID: {matches[0]['id']})", "INFO")
        return matches[0]
    elif len(matches) > 1:
        logger(f"Found multiple partial matches for studio name: {name}", "INFO")
        for i, match in enumerate(matches):
            logger(f"  {i+1}. {match['name']} (ID: {match['id']})", "INFO")
        return None
    else:
        logger(f"No matches found for studio name: {name}", "INFO")
        return None

def parse_args():
    parser = argparse.ArgumentParser(description='Match studios in your Stash database with ThePornDB and StashDB')
    parser.add_argument('--all', action='store_true', help='Process all studios in the database')
    parser.add_argument('--id', type=str, help='Process a single studio with the specified ID')
    parser.add_argument('--name', type=str, help='Process a single studio by name (searches for exact match)')
    parser.add_argument('--host', type=str, help='Stash host (default: 10.10.10.4)')
    parser.add_argument('--port', type=int, help='Stash port (default: 9999)')
    parser.add_argument('--scheme', type=str, choices=['http', 'https'], help='Stash connection scheme (default: http)')
    parser.add_argument('--api-key', type=str, help='Stash API key')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with more verbose logging')
    parser.add_argument('--limit', type=int, help='Limit the number of studios to process when using --all')
    
    return parser.parse_args()

def main():
    # Check if running as a plugin or from command line
    if len(sys.argv) > 1 and sys.argv[1].startswith('--'):
        # Running from command line with arguments
        args = parse_args()
        
        # Update config if command line arguments provided
        if args.host or args.port or args.scheme:
            # Update the API URL if any connection parameters change
            if args.host:
                config['host'] = args.host
            if args.port:
                config['port'] = args.port
            if args.scheme:
                config['scheme'] = args.scheme
                
            # Update the API URL with the new configuration
            global local_api_url
            local_api_url = f"{config['scheme']}://{config['host']}:{config['port']}/graphql"
            
        if args.api_key:
            config['api_key'] = args.api_key
        
        logger(f"Starting Stash Studio Match Scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
        
        if args.id:
            logger(f"Running in command line mode for studio ID: {args.id}", "INFO")
            update_single_studio(args.id)
        elif args.name:
            logger(f"Running in command line mode for studio name: {args.name}", "INFO")
            studio = find_studio_by_name(args.name)
            if studio:
                update_studio_data(studio)
            else:
                logger(f"Could not find a unique studio with name: {args.name}", "ERROR")
        elif args.all:
            logger("Running in command line mode to update all studios", "INFO")
            update_all_studios()
        else:
            logger("No action specified. Use --all, --id, or --name", "INFO")
            
        logger(f"Stash Studio Match Scrape completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
    else:
        # Running as a plugin or without arguments
        logger(f"Starting Stash Studio Match Scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
        
        # Check for plugin input from stdin
        try:
            if not sys.stdin.isatty():  # Check if stdin has data
                plugin_input = json.loads(sys.stdin.read())
                server_connection = plugin_input.get('server_connection', {})
                plugin_args = plugin_input.get('args', {})
                mode = plugin_args.get('mode', 'all')
                
                # Get plugin settings
                plugin_settings = get_plugin_settings(server_connection)
                hooks_enabled = plugin_settings.get('enableHooks', True)
                
                if mode == 'hook':
                    # Check if hooks are enabled
                    if not hooks_enabled:
                        logger("Automatic updates are disabled. Skipping hook processing.", "INFO")
                        return
                        
                    # Running as a hook
                    hook_context = plugin_input.get('hookContext', {})
                    studio_id = hook_context.get('id')
                    if studio_id:
                        logger(f"Running in hook mode for studio ID: {studio_id}", "INFO")
                        update_single_studio(studio_id)
                    else:
                        logger("No studio ID provided in the hook context.", "ERROR")
                else:
                    # Default to processing all studios
                    logger("Running in task mode to update all studios", "INFO")
                    update_all_studios()
            else:
                # No stdin data, run in batch mode
                logger("Running in batch mode to update all studios", "INFO")
                update_all_studios()
        except json.JSONDecodeError:
            logger("Failed to decode JSON input, running in batch mode", "INFO")
            update_all_studios()
        except Exception as e:
            logger(f"Error processing plugin input: {str(e)}", "ERROR")
            update_all_studios()
            
        logger(f"Stash Studio Match Scrape completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")

# Function to get plugin settings from Stash
def get_plugin_settings(server_connection):
    try:
        # Build the GraphQL query to get plugin settings
        query = """
        query {
            configuration {
                plugins {
                    id
                    name
                    settings
                }
            }
        }
        """
        
        # Get the server details
        scheme = server_connection.get('Scheme', config['scheme'])
        host = server_connection.get('Host', config['host'])
        port = server_connection.get('Port', config['port'])
        api_url = f"{scheme}://{host}:{port}/graphql"
        
        # Get the session cookie
        session_cookie = server_connection.get('SessionCookie', {})
        cookies = {}
        if session_cookie and session_cookie.get('Name') and session_cookie.get('Value'):
            cookies[session_cookie.get('Name')] = session_cookie.get('Value')
        
        # Make the request
        response = requests.post(
            api_url,
            json={'query': query},
            cookies=cookies
        )
        
        if response.status_code == 200:
            data = response.json()
            plugins = data.get('data', {}).get('configuration', {}).get('plugins', [])
            
            # Find our plugin
            for plugin in plugins:
                if plugin.get('name') == 'Studio Match Scrape':
                    settings = plugin.get('settings', {})
                    logger(f"Found plugin settings: {settings}", "DEBUG")
                    return settings
            
            logger("Plugin settings not found, using defaults", "INFO")
            return {'enableHooks': True}
        else:
            logger(f"Failed to get plugin settings: {response.status_code}", "ERROR")
            return {'enableHooks': True}
    except Exception as e:
        logger(f"Error getting plugin settings: {str(e)}", "ERROR")
        return {'enableHooks': True}

if __name__ == "__main__":
    main() 