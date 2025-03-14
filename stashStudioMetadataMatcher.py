#!/usr/bin/env python3
"""
StashStudioMetadataMatcher

A Python script/plugin for matching studios in Stashapp database with ThePornDB and StashDB.


GitHub: https://github.com/pedrolara-boop/StashStudioMetadataMatcher
License: MIT
"""

import requests
import stashapi.log as log
from datetime import datetime, timedelta
import time
import json
import sys
import os
import argparse
import importlib.util
# Import only the fuzz module for token_sort_ratio
from thefuzz import fuzz

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Try to import the user's config file, fall back to template if not available
try:
    # First try to import the user's config
    config_path = os.path.join(script_dir, 'config.py')
    if os.path.exists(config_path):
        spec = importlib.util.spec_from_file_location("config", config_path)
        if spec is not None and spec.loader is not None:
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            config = config_module.config
            print("Using configuration from config.py")
        else:
            raise ImportError("Could not load config.py")
    else:
        # Fall back to template config
        template_path = os.path.join(script_dir, 'config_template.py')
        if os.path.exists(template_path):
            spec = importlib.util.spec_from_file_location("config_template", template_path)
            if spec is not None and spec.loader is not None:
                config_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config_module)
                config = config_module.config
                print("Using configuration from config_template.py")
                print("WARNING: You are using template configuration. Please copy config_template.py to config.py and update with your credentials.")
            else:
                raise ImportError("Could not load config_template.py")
        else:
            raise ImportError("Could not find config.py or config_template.py")
except ImportError as e:
    print(f"Import error: {e}")
    # If neither exists, define a default config
    config = {
        'scheme': 'http',
        'host': 'localhost',
        'port': 9999,
        'api_key': '',
        'tpdb_api_key': '',
        'stashdb_api_key': '',
        'log_file': 'studio_metadata_matcher.log',
        'fuzzy_threshold': 85,  # Default threshold for fuzzy matching (0-100)
        'use_fuzzy_matching': True,  # Enable fuzzy matching by default
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
    
    # Always use our config values for local endpoint
    if endpoint == local_api_url or 'localhost' in endpoint:
        actual_endpoint = f"{config['scheme']}://{config['host']}:{config['port']}/graphql"
        logger(f"Using configured endpoint: {actual_endpoint} instead of {endpoint}", "DEBUG")
    else:
        actual_endpoint = endpoint
    
    # Use a longer timeout for mutation operations (updates, creates)
    if "mutation" in query.lower():
        timeout = 60  # 60 seconds for mutations
    else:
        timeout = 15  # 15 seconds for queries
    
    for attempt in range(retries):
        try:
            logger(f"Making GraphQL request to {actual_endpoint}", "DEBUG")
            # Add timeout to prevent hanging
            response = requests.post(actual_endpoint, json={'query': query, 'variables': variables}, headers=headers, timeout=timeout)
            
            # Log response status for debugging
            logger(f"GraphQL response status: {response.status_code}", "DEBUG")
            
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
                logger(f"Retrying in {sleep_time} seconds...", "DEBUG")
                time.sleep(sleep_time)
            else:
                logger("Max retries reached. Giving up.", "ERROR")
                raise

def find_local_studio(studio_id):
    logger(f"🔍 Finding local studio with ID: {studio_id}", "INFO")
    response = graphql_request(local_find_studio_query, {'id': studio_id}, local_api_url, config['api_key'])
    if response:
        return response.get('findStudio')
    return None

def get_all_studios():
    logger("📋 Getting all studios from local database", "INFO")
    response = graphql_request(all_studios_query, {}, local_api_url, config['api_key'])
    if response:
        studios = response.get('allStudios')
        logger(f"📊 Found {len(studios)} studios in local database", "INFO")
        return studios
    return []

def search_studio(term, api_url, api_key):
    logger(f"Searching for studio '{term}' on {api_url}", "DEBUG")
    
    # Use different queries for different APIs
    if "theporndb.net" in api_url:
        # ThePornDB now uses a REST API for sites
        return search_tpdb_site(term, api_key)
    else:
        query = search_studio_query_stashdb
        response = graphql_request(query, {'term': term}, api_url, api_key)
        if response:
            results = response.get('searchStudio', [])
            logger(f"Found {len(results)} results for '{term}' on {api_url}", "DEBUG")
            return results
    
    return []

def search_tpdb_site(term, api_key):
    """Search for a site on ThePornDB using the REST API"""
    logger(f"Searching for site '{term}' on ThePornDB REST API", "DEBUG")
    
    # Check if API key is provided
    if not api_key:
        logger("No ThePornDB API key provided, skipping search", "DEBUG")
        return []
    
    url = f"{tpdb_rest_api_url}/sites"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }
    params = {
        'q': term
    }
    
    try:
        # Add timeout to prevent hanging
        logger(f"Making request to {url} with query: {term}", "DEBUG")
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'data' in data:
            sites = data['data']
            logger(f"Found {len(sites)} results for '{term}' on ThePornDB REST API", "DEBUG")
            
            # Convert to the same format as our GraphQL results
            results = []
            for site in sites:
                results.append({
                    'id': str(site.get('uuid')),  # Use UUID instead of numeric ID
                    'name': site.get('name')
                })
            return results
        else:
            logger(f"No 'data' field in ThePornDB response: {data}", "DEBUG")
        return []
    except requests.exceptions.RequestException as e:
        logger(f"ThePornDB REST API request failed: {e}", "ERROR")
        return []
    except Exception as e:
        logger(f"Unexpected error in search_tpdb_site: {e}", "ERROR")
        return []

def find_studio(studio_id, api_url, api_key):
    logger(f"Finding studio with ID {studio_id} on {api_url}", "DEBUG")
    
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
    logger(f"Finding site with ID {site_id} on ThePornDB REST API", "DEBUG")
    
    url = f"{tpdb_rest_api_url}/sites/{site_id}"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }
    
    try:
        # Add timeout to prevent hanging
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        
        # The API returns data wrapped in a 'data' object
        if 'data' in response_data:
            site = response_data['data']
            logger(f"Retrieved raw site data from ThePornDB REST API: {site}", "DEBUG")
            
            # Convert to the same format as our GraphQL results
            parent = None
            # Only get parent info if parent_id exists and is not null
            if site.get('parent_id'):
                # Instead of making another API call, use the parent info already in the response
                if site.get('parent') and site['parent'].get('id') and site['parent'].get('name'):
                    parent = {
                        'id': str(site['parent'].get('uuid')),  # Use UUID instead of numeric ID
                        'name': site['parent'].get('name')
                    }
                # If parent info is not in the response, only make an API call if absolutely necessary
                else:
                    try:
                        parent_response = requests.get(f"{tpdb_rest_api_url}/sites/{site.get('parent_id')}", headers=headers, timeout=10)
                        parent_response.raise_for_status()
                        parent_data = parent_response.json()
                        if 'data' in parent_data:
                            parent_site = parent_data['data']
                            parent = {
                                'id': str(parent_site.get('uuid')),  # Use UUID instead of numeric ID
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
                    'id': str(network.get('uuid')),  # Use UUID instead of numeric ID
                    'name': network.get('name')
                }
            
            # Build the result in the same format as StashDB
            result = {
                'id': str(site.get('uuid')),  # Use UUID instead of numeric ID
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
            
            logger(f"Processed site data from ThePornDB REST API: {result}", "DEBUG")
            return result
        
        logger(f"No data found in ThePornDB REST API response for site ID {site_id}", "ERROR")
        return None
    except requests.exceptions.RequestException as e:
        logger(f"ThePornDB REST API request failed: {e}", "ERROR")
        return None

def find_or_create_parent_studio(parent_data, api_url, dry_run=False):
    """Find a parent studio in the local database or create it if it doesn't exist"""
    if not parent_data:
        return None
    
    parent_id = parent_data.get('id')
    parent_name = parent_data.get('name')
    
    if not parent_id or not parent_name:
        return None
    
    logger(f"Looking for parent studio: {parent_name} (ID: {parent_id} on {api_url})", "DEBUG")
    
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
                            logger(f"Found parent studio by StashDB ID: {studio['name']} (ID: {studio['id']})", "DEBUG")
                            
                            # Check if this is a ThePornDB ID and the studio doesn't have a ThePornDB ID yet
                            if "theporndb" in api_url.lower() and not any(s.get('endpoint') == 'https://theporndb.net/graphql' for s in studio.get('stash_ids', [])):
                                # Add ThePornDB ID to the studio
                                try:
                                    add_tpdb_id_to_studio(studio['id'], parent_id, dry_run)
                                except Exception as e:
                                    logger(f"Error adding ThePornDB ID to parent studio: {e}", "ERROR")
                                    # Continue even if this fails
                            
                            return studio['id']
            
            # If not found by StashDB ID, look for exact match by name
            for studio in studios:
                if studio['name'].lower() == parent_name.lower():
                    logger(f"Found parent studio by name: {studio['name']} (ID: {studio['id']})", "DEBUG")
                    
                    # Add the stash_id to the parent studio
                    update_mutation = """
                    mutation UpdateStudio($input: StudioUpdateInput!) {
                        studioUpdate(input: $input) {
                            id
                            name
                        }
                    }
                    """
                    
                    # Get existing stash_ids
                    existing_stash_ids = []
                    if studio.get('stash_ids'):
                        existing_stash_ids = studio['stash_ids']
                    
                    # Add the new stash_id if it doesn't already exist
                    if not any(s.get('endpoint') == api_url and s.get('stash_id') == parent_id for s in existing_stash_ids):
                        existing_stash_ids.append({
                            'stash_id': parent_id,
                            'endpoint': api_url
                        })
                    
                    variables = {
                        'input': {
                            'id': studio['id'],
                            'stash_ids': existing_stash_ids
                        }
                    }
                    
                    if dry_run:
                        logger(f"🔄 DRY RUN: Would add stash_id to parent studio: {studio['name']} (ID: {studio['id']})", "INFO")
                    else:
                        try:
                            graphql_request(update_mutation, variables, local_api_url, config['api_key'])
                            logger(f"Added stash_id to parent studio: {studio['name']} (ID: {studio['id']})", "DEBUG")
                        except Exception as e:
                            logger(f"Error adding stash_id to parent studio: {e}", "ERROR")
                            # Continue even if this fails
                    
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
        
        if dry_run:
            logger(f"🔄 DRY RUN: Would create parent studio: {parent_name}", "INFO")
            return "dry-run-parent-id"
        else:
            try:
                response = graphql_request(create_mutation, variables, local_api_url, config['api_key'])
                
                if response and response.get('studioCreate'):
                    parent_studio = response['studioCreate']
                    logger(f"➕ Created parent studio: {parent_studio['name']} (ID: {parent_studio['id']})", "INFO")
                    return parent_studio['id']
            except Exception as e:
                logger(f"Error creating parent studio: {e}", "ERROR")
                # Return None to avoid hanging
        
        logger(f"Failed to create parent studio: {parent_name}", "ERROR")
        return None
    except Exception as e:
        logger(f"Error finding or creating parent studio: {e}", "ERROR")
        return None

def add_tpdb_id_to_studio(studio_id, tpdb_id, dry_run=False):
    """Add a ThePornDB ID to a studio that already exists"""
    logger(f"Adding ThePornDB ID {tpdb_id} to studio {studio_id}", "DEBUG")
    
    # First get the current studio data
    find_studio_query = """
    query FindStudio($id: ID!) {
        findStudio(id: $id) {
            id
            name
            stash_ids {
                endpoint
                stash_id
            }
        }
    }
    """
    
    try:
        response = graphql_request(find_studio_query, {'id': studio_id}, local_api_url, config['api_key'])
        if not response or not response.get('findStudio'):
            logger(f"Could not find studio with ID {studio_id}", "ERROR")
            return
        
        studio = response['findStudio']
        
        # Get existing stash_ids
        existing_stash_ids = []
        if studio.get('stash_ids'):
            existing_stash_ids = studio['stash_ids']
        
        # Check if the ThePornDB ID already exists
        if any(s.get('endpoint') == 'https://theporndb.net/graphql' and s.get('stash_id') == tpdb_id for s in existing_stash_ids):
            logger(f"Studio {studio['name']} already has ThePornDB ID {tpdb_id}", "DEBUG")
            return
        
        # Add the ThePornDB ID
        existing_stash_ids.append({
            'stash_id': tpdb_id,
            'endpoint': 'https://theporndb.net/graphql'
        })
        
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
                'id': studio_id,
                'stash_ids': existing_stash_ids
            }
        }
        
        if dry_run:
            logger(f"🔄 DRY RUN: Would add ThePornDB ID {tpdb_id} to studio {studio['name']} (ID: {studio_id})", "INFO")
        else:
            try:
                response = graphql_request(update_mutation, variables, local_api_url, config['api_key'])
                if response and response.get('studioUpdate'):
                    logger(f"🔗 Added ThePornDB ID {tpdb_id} to studio {studio['name']} (ID: {studio_id})", "INFO")
            except Exception as e:
                logger(f"Error adding ThePornDB ID to studio: {e}", "ERROR")
                # Don't raise the exception, just log it
    except Exception as e:
        logger(f"Error in add_tpdb_id_to_studio: {e}", "ERROR")
        # Don't raise the exception, just log it

def update_studio(studio_data, local_id, dry_run=False):
    logger(f"📝 Updating studio with ID: {local_id}", "INFO")
    studio_data['id'] = local_id
    variables = {'input': studio_data}

    if dry_run:
        logger(f"🔄 DRY RUN: Would update studio {local_id} with data: {studio_data}", "INFO")
        return studio_data
    else:
        response = graphql_request(studio_update_mutation, variables, local_api_url, config['api_key'])
        if response:
            return response.get('studioUpdate')
        return None

def fuzzy_match_studio_name(name, candidates, threshold=85):
    """
    Find the best fuzzy match for a studio name from a list of candidates.
    
    Args:
        name (str): The studio name to match
        candidates (list): List of candidate studio dictionaries with 'name' key
        threshold (int): Minimum score (0-100) to consider a match
        
    Returns:
        tuple: (best_match, score) or (None, 0) if no match above threshold
    """
    if not name or not candidates:
        return None, 0
    
    best_match = None
    best_score = 0
    
    # Compare each candidate and find the best match
    for candidate in candidates:
        candidate_name = candidate['name']
        # Use token_sort_ratio for better matching of words in different orders
        score = fuzz.token_sort_ratio(name.lower(), candidate_name.lower())
        
        if score > best_score:
            best_score = score
            best_match = candidate
    
    # Only return matches above the threshold
    if best_score >= threshold and best_match is not None:
        logger(f"Fuzzy matched '{name}' to '{best_match['name']}' with score {best_score}", "DEBUG")
        return best_match, best_score
    
    return None, 0

def update_studio_data(studio, dry_run=False, force=False):
    logger(f"🔍 Analyzing studio: '{studio['name']}' (ID: {studio['id']})", "INFO")

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
    
    logger(f"Studio {studio['name']} has TPDB ID: {has_tpdb_id} ({tpdb_id if tpdb_id else 'None'}), StashDB ID: {has_stashdb_id} ({stashdb_id if stashdb_id else 'None'}), Parent: {has_parent}", "DEBUG")

    # If force is not enabled and the studio already has all information, skip it
    if not force and has_tpdb_id and has_stashdb_id and has_parent:
        logger(f"✅ Studio '{studio['name']}' is complete - no updates needed", "INFO")
        return False

    # If force is enabled, log that we're forcing an update
    if force and has_tpdb_id and has_stashdb_id and has_parent:
        logger(f"🔄 Force updating studio '{studio['name']}' even though it's already complete", "INFO")

    # Search for matches on both ThePornDB and StashDB
    tpdb_match = None
    stashdb_match = None
    
    # Only search ThePornDB if we don't have a TPDB ID or force is enabled, and the API key is set
    if (not has_tpdb_id or force) and config['tpdb_api_key']:
        try:
            tpdb_results = search_studio(studio['name'], tpdb_api_url, config['tpdb_api_key'])
            if tpdb_results:
                # First try exact matches
                exact_matches = [result for result in tpdb_results if result['name'].lower() == studio['name'].lower()]

                if len(exact_matches) == 1:
                    tpdb_match = exact_matches[0]
                    logger(f"🎯 Found exact match on ThePornDB: {tpdb_match['name']} (ID: {tpdb_match['id']})", "INFO")
                elif len(exact_matches) > 1:
                    logger(f"⚠️ Skipping {studio['name']} - Multiple exact matches found on ThePornDB", "INFO")
                else:
                    # If no exact match, try fuzzy matching if enabled
                    if config.get('use_fuzzy_matching', True):
                        fuzzy_match, score = fuzzy_match_studio_name(
                            studio['name'], 
                            tpdb_results, 
                            config.get('fuzzy_threshold', 85)
                        )
                        if fuzzy_match:
                            tpdb_match = fuzzy_match
                            logger(f"🎯 Found fuzzy match on ThePornDB: {tpdb_match['name']} (ID: {tpdb_match['id']}, score: {score})", "INFO")
                        else:
                            logger(f"❓ No fuzzy match found on ThePornDB for: {studio['name']}", "DEBUG")
                    else:
                        logger(f"❓ No exact match found on ThePornDB for: {studio['name']}", "DEBUG")
        except Exception as e:
            logger(f"Error searching ThePornDB: {e}", "ERROR")
            # Continue with StashDB search even if ThePornDB search fails
    
    # Search for the studio on StashDB if we don't have a StashDB ID or force is enabled, and the API key is set
    if (not has_stashdb_id or force) and config['stashdb_api_key']:
        try:
            stashdb_results = search_studio(studio['name'], stashdb_api_url, config['stashdb_api_key'])
            if stashdb_results:
                # First try exact matches
                exact_matches = [result for result in stashdb_results if result['name'].lower() == studio['name'].lower()]

                if len(exact_matches) == 1:
                    stashdb_match = exact_matches[0]
                    logger(f"🎯 Found exact match on StashDB: {stashdb_match['name']} (ID: {stashdb_match['id']})", "INFO")
                elif len(exact_matches) > 1:
                    logger(f"⚠️ Skipping {studio['name']} - Multiple exact matches found on StashDB", "INFO")
                else:
                    # If no exact match, try fuzzy matching if enabled
                    if config.get('use_fuzzy_matching', True):
                        fuzzy_match, score = fuzzy_match_studio_name(
                            studio['name'], 
                            stashdb_results, 
                            config.get('fuzzy_threshold', 85)
                        )
                        if fuzzy_match:
                            stashdb_match = fuzzy_match
                            logger(f"🎯 Found fuzzy match on StashDB: {stashdb_match['name']} (ID: {stashdb_match['id']}, score: {score})", "INFO")
                        else:
                            logger(f"❓ No fuzzy match found on StashDB for: {studio['name']}", "DEBUG")
                    else:
                        logger(f"❓ No exact match found on stashDB for: {studio['name']}", "DEBUG")
        except Exception as e:
            logger(f"Error searching StashDB: {e}", "ERROR")

    # Get studio data from both APIs if we have matches or existing IDs
    tpdb_studio_data = None
    stashdb_studio_data = None
    
    # Get ThePornDB data if we have a match or an existing ID and the API key is set
    if config['tpdb_api_key']:
        try:
            if tpdb_match:
                tpdb_studio_data = find_studio(tpdb_match['id'], tpdb_api_url, config['tpdb_api_key'])
                if tpdb_studio_data:
                    logger(f"Retrieved ThePornDB data using matched ID: {tpdb_match['id']}", "DEBUG")
            elif tpdb_id:
                # If we already have a ThePornDB ID but no match (because we didn't search), get the data directly
                tpdb_studio_data = find_studio(tpdb_id, tpdb_api_url, config['tpdb_api_key'])
                if tpdb_studio_data:
                    logger(f"Retrieved ThePornDB data using existing ID: {tpdb_id}", "DEBUG")
        except Exception as e:
            logger(f"Error retrieving ThePornDB data: {e}", "ERROR")
            # Continue with StashDB data even if ThePornDB data retrieval fails
    
    # Get StashDB data if we have a match or an existing ID and the API key is set
    if config['stashdb_api_key']:
        try:
            if stashdb_match:
                stashdb_studio_data = find_studio(stashdb_match['id'], stashdb_api_url, config['stashdb_api_key'])
                if stashdb_studio_data:
                    logger(f"Retrieved StashDB data using matched ID: {stashdb_match['id']}", "DEBUG")
            elif stashdb_id:
                # If we already have a StashDB ID but no match (because we didn't search), get the data directly
                stashdb_studio_data = find_studio(stashdb_id, stashdb_api_url, config['stashdb_api_key'])
                if stashdb_studio_data:
                    logger(f"Retrieved StashDB data using existing ID: {stashdb_id}", "DEBUG")
        except Exception as e:
            logger(f"Error retrieving StashDB data: {e}", "ERROR")

    # Check if we need to update anything (new IDs or parent studio)
    need_update = force or (tpdb_match and not has_tpdb_id) or (stashdb_match and not has_stashdb_id) or (not has_parent and ((tpdb_studio_data and 'parent' in tpdb_studio_data and tpdb_studio_data['parent']) or (stashdb_studio_data and 'parent' in stashdb_studio_data and stashdb_studio_data['parent'])))
    
    if need_update or (stashdb_studio_data and 'parent' in stashdb_studio_data and stashdb_studio_data['parent']) or (tpdb_studio_data and 'parent' in tpdb_studio_data and tpdb_studio_data['parent']):
        # Combine data from both sources, with StashDB taking precedence
        combined_data = {}
        if tpdb_studio_data:
            combined_data.update(tpdb_studio_data)
            logger(f"Got studio data from ThePornDB: {tpdb_studio_data}", "DEBUG")
        if stashdb_studio_data:
            combined_data.update(stashdb_studio_data)
            logger(f"Got studio data from StashDB: {stashdb_studio_data}", "DEBUG")

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
        parent_name = None
        try:
            if stashdb_studio_data and 'parent' in stashdb_studio_data and stashdb_studio_data['parent']:
                parent_id = find_or_create_parent_studio(stashdb_studio_data['parent'], stashdb_api_url, dry_run)
                if parent_id:
                    parent_name = stashdb_studio_data['parent'].get('name')
                    logger(f"Found parent studio ID from StashDB: {parent_id} for studio: {studio['name']}", "DEBUG")
            elif tpdb_studio_data and 'parent' in tpdb_studio_data and tpdb_studio_data['parent']:
                parent_id = find_or_create_parent_studio(tpdb_studio_data['parent'], tpdb_api_url, dry_run)
                if parent_id:
                    parent_name = tpdb_studio_data['parent'].get('name')
                    logger(f"Found parent studio ID from ThePornDB: {parent_id} for studio: {studio['name']}", "DEBUG")
        except Exception as e:
            logger(f"Error finding or creating parent studio: {e}", "ERROR")
            # Continue with the update even if parent studio creation fails

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
        new_tpdb_id = None
        if tpdb_match and not any(s['endpoint'] == 'https://theporndb.net/graphql' and s['stash_id'] == tpdb_match['id'] for s in new_stash_ids):
            new_stash_ids.append({
                'stash_id': tpdb_match['id'],
                'endpoint': "https://theporndb.net/graphql"
            })
            new_tpdb_id = tpdb_match['id']
            logger(f"Adding ThePornDB ID: {tpdb_match['id']}", "DEBUG")
        
        # Add new StashDB ID if needed
        new_stashdb_id = None
        if stashdb_match and not any(s['endpoint'] == 'https://stashdb.org/graphql' and s['stash_id'] == stashdb_match['id'] for s in new_stash_ids):
            new_stash_ids.append({
                'stash_id': stashdb_match['id'],
                'endpoint': "https://stashdb.org/graphql"
            })
            new_stashdb_id = stashdb_match['id']
            logger(f"Adding StashDB ID: {stashdb_match['id']}", "DEBUG")

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
            logger(f"Prepared studio update data: {studio_update_data}", "DEBUG")
            
            # Build a human-readable summary of updates
            updates = []
            if 'name' in studio_update_data:
                updates.append("name")
            if 'url' in studio_update_data:
                updates.append("URL")
            if 'image' in studio_update_data:
                updates.append("image")
            if new_tpdb_id:
                updates.append(f"ThePornDB ID ({new_tpdb_id})")
            if new_stashdb_id:
                updates.append(f"StashDB ID ({new_stashdb_id})")
            if parent_id and not has_parent:
                if parent_name:
                    updates.append(f"parent studio '{parent_name}'")
                else:
                    updates.append("parent studio")
                
            update_summary = ", ".join(updates)
            if dry_run:
                logger(f"🔄 Studio '{studio['name']}' needs updates: {update_summary}", "INFO")
            else:
                logger(f"📝 Updating studio '{studio['name']}' with: {update_summary}", "INFO")

            try:
                update_result = update_studio(studio_update_data, studio['id'], dry_run)
                if update_result:
                    if dry_run:
                        logger(f"🔄 DRY RUN: Would update studio '{studio['name']}'", "INFO")
                    else:
                        logger(f"✅ Successfully updated studio '{studio['name']}'", "INFO")
                    return True
                else:
                    logger(f"No new details added for studio {studio['name']} (ID: {studio['id']}) - already up to date.", "DEBUG")
                    return False
            except requests.exceptions.HTTPError as e:
                logger(f"Failed to update studio: {studio['name']} (ID: {studio['id']})", "ERROR")
                logger(str(e), "ERROR")
                return False
        else:
            logger(f"No new details to update for studio {studio['name']} (ID: {studio['id']})", "DEBUG")
            return False
    else:
        logger(f"✅ Studio '{studio['name']}' is complete - no updates needed", "INFO")
        return False

def update_all_studios(dry_run=False, force=False):
    studios = get_all_studios()
    
    # Check if we have a limit set
    args = parse_args()
    if args.limit and args.limit > 0 and args.limit < len(studios):
        logger(f"🔢 Limiting to first {args.limit} studios", "INFO")
        studios = studios[:args.limit]
    
    total_studios = len(studios)
    processed_count = 0
    updated_count = 0
    already_complete_count = 0
    start_time = time.time()
    
    mode_str = " (FORCE)" if force else " (DRY RUN)" if dry_run else ""
    logger(f"🚀 Starting update of {total_studios} studios{mode_str}", "INFO")

    # Create a set to track processed studios to avoid duplicates
    processed_studios = set()

    for studio in studios:
        studio_id = studio['id']
        
        # Skip if we've already processed this studio
        if studio_id in processed_studios:
            logger(f"Skipping already processed studio: {studio['name']} (ID: {studio_id})", "DEBUG")
            continue
            
        # Add to processed set
        processed_studios.add(studio_id)
        
        # Process the studio
        # Check if the studio already has all IDs and parent
        has_tpdb_id = any(stash['endpoint'] == 'https://theporndb.net/graphql' for stash in studio['stash_ids'])
        has_stashdb_id = any(stash['endpoint'] == 'https://stashdb.org/graphql' for stash in studio['stash_ids'])
        has_parent = studio.get('parent_studio') is not None
        
        # If force is enabled, always update the studio
        # Otherwise, only update if it's missing information
        if force or not (has_tpdb_id and has_stashdb_id and has_parent):
            was_updated = update_studio_data(studio, dry_run, force)
            if was_updated:
                updated_count += 1
            elif has_tpdb_id and has_stashdb_id and has_parent:
                already_complete_count += 1
        else:
            logger(f"✅ Studio '{studio['name']}' is complete - no updates needed", "INFO")
            already_complete_count += 1

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
        
        # Only log every 10 studios or at the beginning/end to reduce verbosity
        if processed_count % 10 == 0 or processed_count == 1 or processed_count == total_studios:
            logger(f"⏳ Processed {processed_count}/{total_studios} studios ({progress_percentage*100:.2f}%) - ETA: {eta_str}", "INFO")
        else:
            logger(f"⏳ Processed {processed_count}/{total_studios} studios ({progress_percentage*100:.2f}%) - ETA: {eta_str}", "DEBUG")

    # Log completion
    total_time = time.time() - start_time
    logger(f"✅ Completed update of {total_studios} studios in {str(timedelta(seconds=int(total_time)))}", "INFO")
    logger(f"📊 Summary: {updated_count} studios updated, {already_complete_count} studios already complete", "INFO")

def update_single_studio(studio_id, dry_run=False, force=False):
    studio = find_local_studio(studio_id)
    if studio:
        update_studio_data(studio, dry_run, force)
    else:
        logger(f"❌ Studio with ID {studio_id} not found.", "ERROR")

def find_studio_by_name(name):
    logger(f"🔍 Searching for studio with name: {name}", "INFO")
    studios = get_all_studios()
    
    # Look for exact match first
    for studio in studios:
        if studio['name'].lower() == name.lower():
            logger(f"🎯 Found exact match for studio name: {name} (ID: {studio['id']})", "INFO")
            return studio
    
    # If no exact match and fuzzy matching is enabled, try fuzzy matching
    if config.get('use_fuzzy_matching', True):
        fuzzy_match, score = fuzzy_match_studio_name(
            name, 
            studios, 
            config.get('fuzzy_threshold', 85)
        )
        if fuzzy_match:
            logger(f"🎯 Found fuzzy match for studio name: {name} → {fuzzy_match['name']} (ID: {fuzzy_match['id']}, score: {score})", "INFO")
            return fuzzy_match
    
    # If no fuzzy match or fuzzy matching is disabled, look for partial matches
    matches = []
    for studio in studios:
        if name.lower() in studio['name'].lower():
            matches.append(studio)
    
    if len(matches) == 1:
        logger(f"🎯 Found one partial match for studio name: {name} (ID: {matches[0]['id']})", "INFO")
        return matches[0]
    elif len(matches) > 1:
        logger(f"⚠️ Found multiple partial matches for studio name: {name}", "INFO")
        for i, match in enumerate(matches):
            logger(f"  {i+1}. {match['name']} (ID: {match['id']})", "INFO")
        return None
    else:
        logger(f"❓ No matches found for studio name: {name}", "INFO")
        return None

def parse_args():
    parser = argparse.ArgumentParser(description='StashStudioMetadataMatcher: Match studios in your Stash database with ThePornDB and StashDB')
    parser.add_argument('--all', action='store_true', help='Process all studios in the database')
    parser.add_argument('--id', type=str, help='Process a single studio with the specified ID')
    parser.add_argument('--name', type=str, help='Process a single studio by name (searches for exact match)')
    parser.add_argument('--host', type=str, help='Stash host (default: 10.10.10.4)')
    parser.add_argument('--port', type=int, help='Stash port (default: 9999)')
    parser.add_argument('--scheme', type=str, choices=['http', 'https'], help='Stash connection scheme (default: http)')
    parser.add_argument('--api-key', type=str, help='Stash API key')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with more verbose logging')
    parser.add_argument('--limit', type=int, help='Limit the number of studios to process when using --all')
    parser.add_argument('--dry-run', action='store_true', help='Show what changes would be made without actually making them')
    parser.add_argument('--force', action='store_true', help='Force update all studios even if they already have all information')
    parser.add_argument('--fuzzy-threshold', type=int, help='Threshold for fuzzy matching (0-100, default: 85)')
    parser.add_argument('--no-fuzzy', action='store_true', help='Disable fuzzy matching')
    
    return parser.parse_args()

def main():
    # Only handle command line arguments in this version
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
        
    # Update fuzzy matching settings if provided
    if args.fuzzy_threshold:
        config['fuzzy_threshold'] = args.fuzzy_threshold
    if args.no_fuzzy:
        config['use_fuzzy_matching'] = False
    
    mode_str = " (FORCE)" if args.force else " (DRY RUN)" if args.dry_run else ""
    fuzzy_str = "" if config['use_fuzzy_matching'] else " (NO FUZZY)"
    logger(f"🚀 Starting StashStudioMetadataMatcher{mode_str}{fuzzy_str}", "INFO")
    
    if args.id:
        logger(f"🔍 Running for studio ID: {args.id}", "INFO")
        update_single_studio(args.id, args.dry_run, args.force)
    elif args.name:
        logger(f"🔍 Running for studio name: {args.name}", "INFO")
        studio = find_studio_by_name(args.name)
        if studio:
            update_studio_data(studio, args.dry_run, args.force)
        else:
            logger(f"❌ Could not find a unique studio with name: {args.name}", "ERROR")
    elif args.all:
        logger("🔄 Running update for all studios", "INFO")
        update_all_studios(args.dry_run, args.force)
    else:
        logger("❓ No action specified. Use --all, --id, --name, or --force", "INFO")
        
    mode_str = " (FORCE)" if args.force else " (DRY RUN)" if args.dry_run else ""
    logger(f"✅ StashStudioMetadataMatcher completed{mode_str}", "INFO")

if __name__ == "__main__":
    main() 