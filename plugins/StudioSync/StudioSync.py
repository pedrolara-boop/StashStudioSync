#!/usr/bin/env python3
"""
StudioSync

A plugin for matching and syncing studios in Stash with ThePornDB and StashDB.
Automatically completes missing studio information including IDs, URLs, images,
and parent relationships.

GitHub: https://github.com/pedrolara-boop/StudioSync
License: MIT
"""

import json
import sys
import requests
from datetime import timedelta
import time
from stashapi.stashapp import StashInterface
import stashapi.log as log
from thefuzz import fuzz
import argparse
import os
import atexit

# Constants for API endpoints
TPDB_API_URL = "https://theporndb.net/graphql"
TPDB_REST_API_URL = "https://api.theporndb.net"
STASHDB_API_URL = "https://stashdb.org/graphql"

# Lock file path
LOCK_FILE = os.path.expanduser("~/.stash/plugins/StudioSync.lock")

# GraphQL queries for standard Stash-box endpoints
STASHBOX_SEARCH_STUDIO_QUERY = """
query SearchStudio($term: String!) {
    searchStudio(term: $term) {
        id
        name
    }
}
"""

STASHBOX_FIND_STUDIO_QUERY = """
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

# GraphQL queries for local Stash instance
LOCAL_FIND_STUDIO_QUERY = """
query FindStudio($id: ID!) {
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
        image_path
    }
}
"""

config = {}  # Initialize empty config dictionary
processed_studios = set()  # Track which studios we've already processed

def logger(message, level="INFO"):
    """
    Unified logging function that uses stashapi.log
    
    Args:
        message: The message to log
        level: Log level (INFO, DEBUG, ERROR, PROGRESS)
    """
    if level == "INFO":
        log.info(message)
    elif level == "DEBUG":
        log.debug(message)
    elif level == "ERROR":
        log.error(message)
    elif level == "PROGRESS":
        log.progress(message)
    else:
        log.info(message)  # Default to INFO for unknown levels

def str_to_bool(value):
    """Convert string or boolean value to boolean"""
    if isinstance(value, bool):
        return value
    return str(value).lower() in ('true', '1', 'yes', 'on')

def acquire_lock():
    """Acquire a lock to prevent multiple instances from running"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())
            # Check if process is still running
            try:
                os.kill(pid, 0)
                # If we get here, the process is still running
                logger(f"Another instance of StudioSync is already running (PID: {pid})", "ERROR")
                return False
            except OSError:
                # Process is not running, we can acquire the lock
                pass
        except (ValueError, IOError):
            pass
    
    try:
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except IOError as e:
        logger(f"Failed to acquire lock: {e}", "ERROR")
        return False

def release_lock():
    """Release the lock"""
    try:
        if os.path.exists(LOCK_FILE):
            # Only remove if it's our lock
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.remove(LOCK_FILE)
            else:
                logger(f"Lock file belongs to different process (PID: {pid})", "ERROR")
    except IOError as e:
        logger(f"Failed to release lock: {e}", "ERROR")
    except ValueError:
        logger("Invalid lock file format", "ERROR")

def main():
    """
    Main function for the plugin version.
    Reads plugin arguments from stdin and processes studios accordingly.
    """
    global config, processed_studios
    
    # Try to acquire lock
    if not acquire_lock():
        logger("Another instance of StudioSync is already running", "ERROR")
        return
    
    # Register lock release on exit
    atexit.register(release_lock)
    
    try:
        # Clear the processed studios set at the start of each plugin run
        processed_studios.clear()
        
        if not sys.stdin.isatty():
            plugin_input = json.loads(sys.stdin.read())
            server_connection = plugin_input.get('server_connection', {})
            plugin_args = plugin_input.get('args', {})
            
            # Create a StashInterface using the server connection details
            stash = StashInterface(server_connection)
            stash_config = stash.get_configuration()
            
            # Initialize config with default values
            config.update({
                'scheme': server_connection.get('Scheme', 'http'),
                'host': server_connection.get('Host', 'localhost'),
                'port': server_connection.get('Port', 9999),
                'api_key': server_connection.get('ApiKey', ''),
                'fuzzy_threshold': 85,
                'use_fuzzy_matching': True,
                'stash_interface': stash,
                'stashbox_endpoints': []
            })
            
            # Get API keys from Stash configuration
            if 'stashBoxes' in stash_config.get('general', {}):
                logger("🔍 Configuring Stash-box endpoints:", "INFO")
                configured_endpoints = set()  # Track unique endpoints
                
                for stash_box in stash_config['general']['stashBoxes']:
                    endpoint = stash_box.get('endpoint', '')
                    api_key = stash_box.get('api_key', '')
                    name = stash_box.get('name', 'Unknown')
                    
                    if endpoint and api_key:
                        # Skip duplicate endpoints
                        if endpoint in configured_endpoints:
                            logger(f"⚠️ Skipping duplicate endpoint: {name} ({endpoint})", "INFO")
                            continue
                            
                        configured_endpoints.add(endpoint)
                        is_tpdb = "theporndb.net" in endpoint.lower()
                        
                        endpoint_info = {
                            'name': name,
                            'endpoint': endpoint,
                            'api_key': api_key,
                            'is_tpdb': is_tpdb
                        }
                        
                        config['stashbox_endpoints'].append(endpoint_info)
                        
                        if is_tpdb:
                            logger(f"✅ Added ThePornDB endpoint: {name}", "INFO")
                        else:
                            logger(f"✅ Added Stash-box endpoint: {name} ({endpoint})", "INFO")
                
                # Summary of configured endpoints
                stashbox_count = len([e for e in config['stashbox_endpoints'] if not e['is_tpdb']])
                has_tpdb = any(e['is_tpdb'] for e in config['stashbox_endpoints'])
                logger(f"📊 Total endpoints configured: {len(config['stashbox_endpoints'])} ({stashbox_count} Stash-boxes, TPDB: {has_tpdb})", "INFO")
            
            # Get plugin arguments
            dry_run = str_to_bool(plugin_args.get('dry_run', False))
            force = str_to_bool(plugin_args.get('force', False))
            studio_id = plugin_args.get('studio_id')
            
            # Make the mode setting visible in the logs at startup
            mode_str = " (FORCE)" if force else " (DRY RUN)" if dry_run else ""
            logger(f"🚀 Starting StudioSync{mode_str} - Fuzzy threshold: {config['fuzzy_threshold']}")
            
            # Process single studio or all studios
            if studio_id:
                logger(f"🔍 Processing single studio ID: {studio_id}")
                studio = find_local_studio(studio_id)
                if studio:
                    # Search for matches
                    matches = search_all_stashboxes(studio['name'])
                    if matches:
                        # Process the studio with matches
                        process_studio_with_matches(studio, matches, dry_run, force)
                    else:
                        logger(f"❌ No matches found for studio: {studio['name']}", "INFO")
                else:
                    logger(f"❌ Studio with ID {studio_id} not found.")
            else:
                logger("🔄 Processing all studios")
                update_all_studios(dry_run, force)
            
            logger("✅ StudioSync completed")
        else:
            print("No input received from stdin. This script is meant to be run as a Stash plugin.")
    except json.JSONDecodeError:
        print("Failed to decode JSON input. This script is meant to be run as a Stash plugin.")
    except Exception as e:
        print(f"Error in StudioSync: {str(e)}")
    finally:
        release_lock()

def search_tpdb_site(term, api_key):
    """Search for a site on ThePornDB using the REST API"""
    logger(f"Searching for site '{term}' on ThePornDB REST API", "DEBUG")
    
    if not api_key:
        logger("No ThePornDB API key provided, skipping search", "DEBUG")
        return []
    
    url = f"{TPDB_REST_API_URL}/sites"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }
    params = {
        'q': term,
        'limit': 100,
        'sort': 'name',
        'status': 'active',
        'include': 'parent,network',
        'order': 'desc'
    }
    
    try:
        logger(f"Making request to {url} with query: {term}", "DEBUG")
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code != 200:
            logger(f"Failed request to: {response.url}", "DEBUG")
        
        response.raise_for_status()
        data = response.json()
        
        if 'data' in data:
            sites = data['data']
            logger(f"Found {len(sites)} results for '{term}' on ThePornDB REST API", "DEBUG")
            
            results = []
            for site in sites:
                # Only include if we have a valid UUID
                if site.get('uuid'):
                    # Handle parent/network relationships
                    parent_info = None
                    if site.get('parent') and site['parent'].get('uuid'):
                        parent_info = {
                            'id': site['parent']['uuid'],  # Use parent UUID
                            'name': site['parent'].get('name')
                        }
                    # Don't use network as parent - networks are separate entities
                    
                    results.append({
                        'id': site['uuid'],  # Use UUID consistently
                        'name': site.get('name'),
                        'parent': parent_info,
                        'date_updated': site.get('updated_at')
                    })
            return results
        else:
            logger(f"No 'data' field in ThePornDB response: {data}", "DEBUG")
            return []
    except requests.exceptions.RequestException as e:
        logger(f"ThePornDB REST API request failed: {e}", "ERROR")
        if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'text'):
            logger(f"Error response: {e.response.text}", "DEBUG")
        return []
    except Exception as e:
        logger(f"Unexpected error in search_tpdb_site: {e}", "ERROR")
        return []

def analyze_available_fields(data, source):
    """Analyze and log available fields in the response data"""
    if not data:
        return
        
    def extract_fields(obj, prefix=''):
        fields = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    fields.extend(extract_fields(value, f"{prefix}{key}."))
                else:
                    fields.append(f"{prefix}{key}")
        elif isinstance(obj, list) and obj:
            fields.extend(extract_fields(obj[0], prefix))
        return fields

    fields = extract_fields(data)
    logger(f"\n🔎 Available fields from {source}:", "INFO")
    logger("Fields we could potentially use:", "INFO")
    for field in sorted(fields):
        logger(f"  - {field}", "INFO")

def find_tpdb_site(site_uuid, api_key):
    """Fetch studio details from ThePornDB using their REST API"""
    try:
        url = f"{TPDB_REST_API_URL}/sites/{site_uuid}"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Log the response for debugging
        logger(f"TPDB REST API response for {site_uuid}: {data}", "DEBUG")
        
        if data and 'data' in data:
            site_data = data['data']
            if not site_data.get('uuid'):
                logger(f"No UUID found in TPDB response for site {site_uuid}", "ERROR")
                return None
            
            # Handle parent relationship
            parent_data = None
            if site_data.get('parent') and site_data['parent'].get('uuid'):
                parent_data = {
                    'id': site_data['parent']['uuid'],  # Use parent UUID
                    'name': site_data['parent'].get('name')
                }
            
            # Construct result using only UUID-based identifiers
            result = {
                'id': site_data['uuid'],
                'name': site_data.get('name'),
                'url': site_data.get('url'),
                'images': [],
                'parent': parent_data
            }
            
            # Add images if available
            if site_data.get('logo'):
                result['images'].append({'url': site_data['logo']})
            if site_data.get('poster'):
                result['images'].append({'url': site_data['poster']})
            
            logger(f"Returning site data for {site_data.get('name')}: {result}", "DEBUG")
            return result
            
        logger(f"No valid data found in TPDB response for {site_uuid}", "DEBUG")
        return None
    except Exception as e:
        logger(f"Error in find_tpdb_site: {str(e)}", "ERROR")
        return None

def calculate_word_order_score(name1, name2):
    """Calculate score based on word order and position with improved weighting"""
    words1 = name1.lower().split()
    words2 = name2.lower().split()
    
    score = 0
    # Words in the same position get higher weight
    for i, (w1, w2) in enumerate(zip(words1, words2)):
        if w1 == w2:
            # Words in the same position get higher weight
            score += 40  # Increased from 30
        elif w1 in words2 or w2 in words1:
            # Words found in different positions get lower weight
            score += 20  # Increased from 15
    
    # Additional penalty for missing words at the start
    if len(words1) > len(words2):
        missing_words = words1[:len(words1)-len(words2)]
        score -= len(missing_words) * 25  # Stronger penalty for missing words at start
    
    return score

def calculate_prefix_suffix_score(name1, name2):
    """Calculate score based on common prefixes and suffixes with improved weighting"""
    name1 = name1.lower()
    name2 = name2.lower()
    
    score = 0
    # Check for common prefixes with higher weight for longer matches
    for i in range(min(len(name1), len(name2))):
        if name1[:i] == name2[:i]:
            score += i * 2  # Weight increases with length of match
    
    # Check for common suffixes with higher weight for longer matches
    for i in range(min(len(name1), len(name2))):
        if name1[-i:] == name2[-i:]:
            score += i * 2  # Weight increases with length of match
    
    return score

def analyze_word_lengths(name1, name2):
    """Analyze word lengths and positions for better matching"""
    words1 = name1.lower().split()
    words2 = name2.lower().split()
    
    score = 0
    # Longer words are more significant
    for w1 in words1:
        if len(w1) > 4:  # Only consider significant words
            if w1 in words2:
                score += 30
            else:
                score -= 20  # Penalty for missing significant words
    
    return score

def fuzzy_match_studio_name(name, candidates, threshold=85):
    """Enhanced matching using multiple strategies"""
    if not name or not candidates:
        return None, 0, []
    
    # Group matches by endpoint for clearer logging
    matches_by_endpoint = {}
    best_matches = []
    overall_best_match = None
    overall_best_score = 0
    
    # Normalize the input name
    name_lower = name.lower()
    name_words = set(name_lower.split())
    name_no_space = name_lower.replace(" ", "")
    
    # Define words that should have negative weights
    negative_words = {
        'network': -30,  # Strong negative weight for "network"
        'group': -25,    # Strong negative weight for "group"
        'media': -25,    # Strong negative weight for "media"
        'entertainment': -25,  # Strong negative weight for "entertainment"
        'productions': -20,     # Medium negative weight for "productions"
        'studio': -20,          # Medium negative weight for "studio"
        'films': -20,           # Medium negative weight for "films"
        'pictures': -20,        # Medium negative weight for "pictures"
        'company': -15,         # Light negative weight for "company"
        'inc': -15,             # Light negative weight for "inc"
        'llc': -15,             # Light negative weight for "llc"
        'ltd': -15              # Light negative weight for "ltd"
    }
    
    # First pass: Check for exact matches
    exact_matches = []
    for candidate in candidates:
        endpoint_name = candidate.get('endpoint_name', 'Unknown')
        candidate_name = candidate['name'].lower()
        
        # Check for exact match (case-insensitive)
        if name_lower == candidate_name:
            exact_matches.append({
                'name': candidate['name'],
                'score': 100,
                'id': candidate['id'],
                'original': candidate,
                'endpoint_name': endpoint_name
            })
            logger(f"   {endpoint_name}: {candidate['name']} (EXACT MATCH)", "INFO")
    
    # If we found exact matches, return the first one (they're all equally valid)
    if exact_matches:
        best_exact_match = exact_matches[0]
        logger(f"✅ Found exact match: '{best_exact_match['name']}' from {best_exact_match['endpoint_name']}", "INFO")
        return best_exact_match['original'], 100, [best_exact_match['original']]
    
    # If no exact matches, proceed with fuzzy matching
    for candidate in candidates:
        endpoint_name = candidate.get('endpoint_name', 'Unknown')
        candidate_name = candidate['name'].lower()
        candidate_words = set(candidate_name.split())
        candidate_no_space = candidate_name.replace(" ", "")
        
        # Calculate multiple similarity scores
        scores = []
        
        # 1. Character-based fuzzy matching (30% weight)
        fuzzy_scores = [
            fuzz.ratio(name_lower, candidate_name),
            fuzz.partial_ratio(name_lower, candidate_name),
            fuzz.token_sort_ratio(name_lower, candidate_name),
            fuzz.token_set_ratio(name_lower, candidate_name)
        ]
        scores.append(max(fuzzy_scores) * 0.3)
        
        # 2. Word order and position (30% weight)
        word_order_score = calculate_word_order_score(name_lower, candidate_name)
        scores.append(word_order_score * 0.3)
        
        # 3. Prefix/Suffix matching (20% weight)
        prefix_suffix_score = calculate_prefix_suffix_score(name_lower, candidate_name)
        scores.append(prefix_suffix_score * 0.2)
        
        # 4. Word length analysis (20% weight)
        word_length_score = analyze_word_lengths(name_lower, candidate_name)
        scores.append(word_length_score * 0.2)
        
        # Calculate final score
        score = sum(scores)
        
        # Apply penalties
        if score >= 90:  # Only apply to high-scoring matches
            # Penalize subset matches
            if (name_words.issubset(candidate_words) or candidate_words.issubset(name_words)) and \
               len(name_words) != len(candidate_words):
                word_diff = abs(len(name_words) - len(candidate_words))
                penalty = word_diff * 15
                score = max(score - penalty, 0)
                logger(f"   Applied word-based penalty of {penalty} points to {candidate_name} (subset match)", "DEBUG")
            
            # Apply negative weights for common words
            for word, weight in negative_words.items():
                if word in candidate_words and word not in name_words:
                    score = max(score + weight, 0)
                    logger(f"   Applied negative weight of {weight} points to {candidate_name} (contains '{word}')", "DEBUG")
                elif word in name_words and word not in candidate_words:
                    score = max(score + weight, 0)
                    logger(f"   Applied negative weight of {weight} points to {candidate_name} (missing '{word}')", "DEBUG")
            
            # Additional penalty for missing significant words
            if len(name_words) > len(candidate_words):
                missing_words = name_words - candidate_words
                for word in missing_words:
                    if len(word) > 4:  # Only penalize for significant words
                        score = max(score - 10, 0)
                        logger(f"   Applied missing word penalty of 10 points to {candidate_name} (missing '{word}')", "DEBUG")
        
        if endpoint_name not in matches_by_endpoint:
            matches_by_endpoint[endpoint_name] = []
        
        matches_by_endpoint[endpoint_name].append({
            'name': candidate['name'],
            'score': score,
            'id': candidate['id'],
            'original': candidate
        })
        
        # Track best match per endpoint and overall
        if score >= threshold:
            if not matches_by_endpoint.get(f"{endpoint_name}_best_score") or score > matches_by_endpoint[f"{endpoint_name}_best_score"]:
                matches_by_endpoint[f"{endpoint_name}_best_score"] = score
                matches_by_endpoint[f"{endpoint_name}_best_match"] = candidate
                
            if score > overall_best_score:
                overall_best_score = score
                overall_best_match = candidate
    
    # Log results by endpoint in a more concise way
    logger(f"🎯 Matches for '{name}':", "INFO")
    for endpoint, matches in matches_by_endpoint.items():
        if isinstance(matches, list):  # Skip our _best_score and _best_match entries
            # Sort matches by score
            sorted_matches = sorted(matches, key=lambda x: x['score'], reverse=True)
            if sorted_matches:
                # Only show top 2 matches per endpoint
                for match in sorted_matches[:2]:
                    match_type = "EXACT" if match['score'] == 100 else "FUZZY"
                    logger(f"   {endpoint}: {match['name']} ({match_type} Score: {match['score']}%)", "INFO")
                
                # If this endpoint had a match above threshold, add it to best matches
                best_for_endpoint = matches_by_endpoint.get(f"{endpoint}_best_match")
                if best_for_endpoint:
                    best_matches.append(best_for_endpoint)
    
    if overall_best_match is not None and overall_best_score >= threshold:
        logger(f"✅ Best match: '{overall_best_match['name']}' from {overall_best_match['endpoint_name']} (Score: {overall_best_score}%)", "INFO")
        return overall_best_match, overall_best_score, best_matches
    else:
        logger(f"❌ No matches above threshold ({threshold}%)", "INFO")
        return None, 0, []

def search_all_stashboxes(studio_name):
    if not config.get('stashbox_endpoints'):
        logger("No endpoints configured", "ERROR")
        return []
        
    results = []
    matches_by_endpoint = {}
    
    for endpoint in config['stashbox_endpoints']:
        try:
            if not endpoint['api_key']:
                continue
                
            if endpoint['is_tpdb']:
                # TPDB search logic
                tpdb_results = search_tpdb_site(studio_name, endpoint['api_key'])
                if tpdb_results:
                    for result in tpdb_results:
                        match_data = {
                            'id': result['id'],
                            'name': result['name'],
                            'endpoint': endpoint['endpoint'],
                            'endpoint_name': endpoint['name'],
                            'api_key': endpoint['api_key'],
                            'is_tpdb': True,
                            'parent': result.get('parent')
                        }
                        results.append(match_data)
                        
                        # Track for reporting
                        if endpoint['name'] not in matches_by_endpoint:
                            matches_by_endpoint[endpoint['name']] = []
                        matches_by_endpoint[endpoint['name']].append(match_data)
            else:
                # Standard Stash-box GraphQL search
                try:
                    response = graphql_request(
                        STASHBOX_SEARCH_STUDIO_QUERY, 
                        {'term': studio_name}, 
                        endpoint['endpoint'], 
                        endpoint['api_key']
                    )
                    
                    if response and 'searchStudio' in response:
                        found_results = response['searchStudio']
                        if found_results:
                            for result in found_results:
                                match_data = {
                                    'id': result['id'],
                                    'name': result['name'],
                                    'endpoint': endpoint['endpoint'],
                                    'endpoint_name': endpoint['name'],
                                    'api_key': endpoint['api_key'],
                                    'is_tpdb': False
                                }
                                results.append(match_data)
                                
                                # Track matches by endpoint
                                if endpoint['name'] not in matches_by_endpoint:
                                    matches_by_endpoint[endpoint['name']] = []
                                matches_by_endpoint[endpoint['name']].append(match_data)
                except Exception as e:
                    logger(f"Error searching {endpoint['name']}: {str(e)}", "ERROR")
                    continue
                
        except Exception as e:
            logger(f"❌ {endpoint['name']} error: {str(e)}", "ERROR")
            continue
    
    # After gathering all results, perform fuzzy matching
    if results:
        best_match, score, all_matches = fuzzy_match_studio_name(studio_name, results)
        logger(f"Found {len(results)} total matches, {len(all_matches)} passed fuzzy matching", "DEBUG")
        
        # Return all matches that passed fuzzy matching
        return results  # Return all results instead of just fuzzy matches
    else:
        logger(f"❌ No matches for '{studio_name}'", "INFO")
        return []

def update_stash_ids(existing_ids, new_id, endpoint):
    """
    Update stash IDs ensuring only one ID per endpoint is maintained.
    
    Args:
        existing_ids (list): List of existing stash IDs
        new_id (str): New stash ID to add
        endpoint (str): Endpoint URL
        
    Returns:
        list: Updated list of stash IDs
    """
    # Remove any existing IDs for this endpoint
    filtered_ids = [sid for sid in existing_ids if sid['endpoint'] != endpoint]
    
    # Add the new ID
    filtered_ids.append({
        'endpoint': endpoint,
        'stash_id': new_id
    })
    
    return filtered_ids

def wrapped_update_studio_data(studio, dry_run=False, force=False):
    """Update studio data with matches from all configured endpoints"""
    global config, processed_studios
    
    studio_id = studio.get('id')
    studio_name = studio['name']
    
    # Check if we've already processed this studio in this session
    if studio_id in processed_studios:
        logger(f"⚠️ Skipping already processed studio: {studio_name}", "DEBUG")
        return False
        
    processed_studios.add(studio_id)  # Mark this studio as processed
    
    # Initialize variables to track all changes
    all_stash_ids = studio.get('stash_ids', []).copy()  # Keep existing stash_ids
    best_image = None
    best_image_score = 0  # Track how good the match is for the image
    best_url = studio.get('url')
    best_parent_id = studio.get('parent_id')
    has_changes = False
    seen_urls = set()
    changes_summary = []
    
    if best_url:
        seen_urls.add(best_url)

    # Search for matches across all endpoints
    matches = search_all_stashboxes(studio_name)
    
    if not matches:
        logger(f"❌ No matches found for: {studio_name}", "INFO")
        return False
    
    # Process each match independently to collect UUIDs from all endpoints
    for match in matches:
        try:
            if match.get('is_tpdb'):
                # Process TPDB match
                studio_data = find_tpdb_site(match['id'], match['api_key'])
                if studio_data:
                    # Update stash_ids using the update function
                    all_stash_ids = update_stash_ids(all_stash_ids, studio_data['id'], match['endpoint'])
                    has_changes = True
                    changes_summary.append("ThePornDB UUID")
                    logger(f"Added/Updated ThePornDB UUID: {studio_data['id']}", "DEBUG")
                    
                    # Handle TPDB images - calculate match score for the logo
                    name_similarity = fuzz.ratio(studio_name.lower(), studio_data['name'].lower())
                    if studio_data.get('images'):
                        for image in studio_data['images']:
                            if image.get('url') and image['url'].startswith(('http://', 'https://')):
                                # Only update if this is a better match
                                if name_similarity > best_image_score:
                                    best_image = image['url']
                                    best_image_score = name_similarity
                                    logger(f"Found better logo match (score: {name_similarity}) from {studio_data['name']}", "DEBUG")
                                    if "logo" not in changes_summary:
                                        changes_summary.append("logo")
                                break
            else:
                # Process Stash-box match
                studio_data = find_stashbox_studio(match['id'], match['endpoint'], match['api_key'])
                if studio_data:
                    # Update stash_ids using the update function
                    all_stash_ids = update_stash_ids(all_stash_ids, studio_data['id'], match['endpoint'])
                    has_changes = True
                    changes_summary.append(f"{match['endpoint_name']} UUID")
                    logger(f"Added/Updated {match['endpoint_name']} UUID: {studio_data['id']}", "DEBUG")
                    
                    # Handle Stash-box images - calculate match score for the logo
                    name_similarity = fuzz.ratio(studio_name.lower(), studio_data['name'].lower())
                    if studio_data.get('images'):
                        for image in studio_data['images']:
                            if image.get('url') and image['url'].startswith(('http://', 'https://')):
                                # Only update if this is a better match
                                if name_similarity > best_image_score:
                                    best_image = image['url']
                                    best_image_score = name_similarity
                                    logger(f"Found better logo match (score: {name_similarity}) from {studio_data['name']}", "DEBUG")
                                    if "logo" not in changes_summary:
                                        changes_summary.append("logo")
                                break
                    
                    # Handle URLs if available
                    if studio_data.get('urls'):
                        for url_data in studio_data['urls']:
                            url = url_data.get('url')
                            if url and url not in seen_urls and url.startswith(('http://', 'https://')):
                                best_url = url
                                seen_urls.add(url)
                                changes_summary.append("URL")
                                break
        except Exception as e:
            logger(f"❌ Error processing match from {match.get('endpoint_name', 'Unknown')}: {str(e)}", "ERROR")
            continue

    # Perform single update with all collected changes
    if has_changes:
        if not dry_run:
            try:
                # Start with required fields
                studio_update = {
                    'id': studio_id,
                    'name': studio_name,
                }
                
                # Only include optional fields if they have valid values
                if best_url:
                    studio_update['url'] = best_url
                if best_parent_id:
                    studio_update['parent_id'] = best_parent_id
                if all_stash_ids:
                    studio_update['stash_ids'] = all_stash_ids
                
                # Only include image if we actually found one and it has a valid URL
                if best_image and isinstance(best_image, str) and best_image.startswith(('http://', 'https://')):
                    studio_update['image'] = best_image
                    logger(f"Adding image URL: {best_image}", "DEBUG")
                
                # Create a concise summary of changes
                unique_changes = list(dict.fromkeys(changes_summary))
                summary = f"📝 {studio_name}: Updated {', '.join(unique_changes)}"
                if force:
                    summary += " (forced update)"
                logger(summary, "INFO")
                
                update_studio(studio_update, studio_id, dry_run)
                return True
            except Exception as e:
                logger(f"❌ Update failed for {studio_name}: {str(e)}", "ERROR")
                return False
        else:
            unique_changes = list(dict.fromkeys(changes_summary))
            logger(f"🔍 [DRY RUN] Would update {studio_name} with: {', '.join(unique_changes)}", "INFO")
            return True
    else:
        logger(f"ℹ️ No changes needed for {studio_name}", "DEBUG")
        return False

def find_stashbox_studio(studio_id, endpoint, api_key):
    """Fetch studio details from a Stash-box endpoint"""
    try:
        response = graphql_request(
            STASHBOX_FIND_STUDIO_QUERY,
            {'id': studio_id},
            endpoint,
            api_key
        )
        
        if response and 'findStudio' in response:
            studio_data = response['findStudio']
            return studio_data
        return None
    except Exception as e:
        logger(f"❌ Error fetching studio from {endpoint}: {str(e)}", "ERROR")
        return None

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Update Stash studios with metadata from ThePornDB and StashDB')
    parser.add_argument('--limit', type=int, help='Limit the number of studios to process')
    return parser.parse_args()

def get_all_studios():
    """Get all studios from Stash"""
    global config
    stash = config.get('stash_interface')
    if not stash:
        logger("No Stash interface configured", "ERROR")
        return []
        
    try:
        # Get all studios first
        studios = stash.find_studios()
        logger(f"Found {len(studios)} total studios in Stash", "INFO")
        
        # Filter studios that need processing
        studios_to_process = []
        for studio in studios:
            # Check if studio needs processing
            needs_processing = False
            
            # Check for missing TPDB ID
            has_tpdb_id = any(stash['endpoint'] == 'https://theporndb.net/graphql' 
                            for stash in studio.get('stash_ids', []))
            if not has_tpdb_id:
                needs_processing = True
                
            # Check for missing StashDB ID
            has_stashdb_id = any(stash['endpoint'] == 'https://stashdb.org/graphql' 
                               for stash in studio.get('stash_ids', []))
            if not has_stashdb_id:
                needs_processing = True
                
            # Check for missing parent studio
            if not studio.get('parent_studio'):
                needs_processing = True
                
            if needs_processing:
                studios_to_process.append(studio)
        
        logger(f"Found {len(studios_to_process)} studios that need processing", "INFO")
        return studios_to_process
        
    except Exception as e:
        logger(f"Error getting studios: {e}", "ERROR")
        return []

def update_all_studios(dry_run=False, force=False):
    """Update all studios with metadata from configured endpoints"""
    # Get studios that need processing
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

    # Group studios by name for batch processing
    studios_by_name = {}
    for studio in studios:
        name = studio['name'].lower()
        if name not in studios_by_name:
            studios_by_name[name] = []
        studios_by_name[name].append(studio)

    # Process each unique studio name
    for name, name_studios in studios_by_name.items():
        # Skip if we've already processed all studios with this name
        if all(studio['id'] in processed_studios for studio in name_studios):
            continue

        # Search for matches once per unique name
        matches = search_all_stashboxes(name)
        
        if matches:
            # Process all studios with this name
            for studio in name_studios:
                studio_id = studio['id']
                
                # Skip if already processed
                if studio_id in processed_studios:
                    continue
                    
                # Process the studio with the matches we found
                was_updated = process_studio_with_matches(studio, matches, dry_run, force)
                if was_updated:
                    updated_count += 1
                else:
                    already_complete_count += 1
                
                processed_studios.add(studio_id)
                processed_count += 1
                
                # Calculate and log progress
                progress_percentage = processed_count / total_studios
                elapsed_time = time.time() - start_time
                
                if processed_count > 0:
                    avg_time_per_studio = elapsed_time / processed_count
                    remaining_studios = total_studios - processed_count
                    eta_seconds = avg_time_per_studio * remaining_studios
                    eta_str = str(timedelta(seconds=int(eta_seconds)))
                else:
                    eta_str = "Unknown"
                
                # Log progress less frequently
                if processed_count % 50 == 0 or processed_count == 1 or processed_count == total_studios:
                    logger(f"⏳ Progress: {processed_count}/{total_studios} ({progress_percentage*100:.1f}%) - ETA: {eta_str}", "INFO")
                else:
                    logger(progress_percentage, "PROGRESS")
        else:
            # Mark all studios with this name as processed
            for studio in name_studios:
                processed_studios.add(studio['id'])
                processed_count += 1
                logger(f"❌ No matches found for: {name}", "INFO")

    # Log completion
    total_time = time.time() - start_time
    logger(f"✅ Completed update of {total_studios} studios in {str(timedelta(seconds=int(total_time)))}", "INFO")
    logger(f"📊 Summary: {updated_count} studios updated, {already_complete_count} studios already complete", "INFO")

def graphql_request(query, variables, endpoint, api_key, retries=5):
    """
    Make a GraphQL request with retries and proper error handling
    
    Args:
        query (str): GraphQL query string
        variables (dict): Variables for the query
        endpoint (str): GraphQL endpoint URL
        api_key (str): API key for authentication
        retries (int): Number of retry attempts
        
    Returns:
        dict: Response data or None if request failed
    """
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Apikey'] = api_key
    
    # Only modify local Stash endpoint
    local_endpoint = f"{config['scheme']}://{config['host']}:{config['port']}/graphql"
    if endpoint == local_endpoint:
        actual_endpoint = local_endpoint
        logger(f"Using local endpoint: {actual_endpoint}", "DEBUG")
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
            response = requests.post(
                actual_endpoint,
                json={'query': query, 'variables': variables},
                headers=headers,
                timeout=timeout
            )
            
            # Only log if there's an error:
            if response.status_code != 200:
                logger(f"Failed request to: {response.url}", "DEBUG")
            
            response.raise_for_status()
            response_json = response.json()
            
            if 'errors' in response_json:
                # Add more detail to the error message
                error_msg = response_json['errors'][0].get('message', 'Unknown GraphQL error')
                logger(f"GraphQL request returned error: {error_msg}", "ERROR")
                return None
                
            return response_json.get('data')
            
        except requests.exceptions.RequestException as e:
            logger(f"GraphQL request failed (attempt {attempt + 1} of {retries}): {e}", "ERROR")
            
            # Log more details about the error if available
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger(f"Error details: {error_detail}", "DEBUG")
                except:
                    logger(f"Raw error response: {e.response.text}", "DEBUG")
            
            if attempt < retries - 1:
                sleep_time = 2 ** attempt  # Exponential backoff
                logger(f"Retrying in {sleep_time} seconds...", "DEBUG")
                time.sleep(sleep_time)
            else:
                logger("Max retries reached. Giving up.", "ERROR")
                raise

def find_local_studio(studio_id):
    """
    Find a studio in the local Stash instance by ID
    
    Args:
        studio_id: The ID of the studio to find
        
    Returns:
        dict: Studio data or None if not found
    """
    logger(f"🔍 Finding local studio with ID: {studio_id}", "INFO")
    
    try:
        # Use the StashInterface object that's already configured
        stash = config.get('stash_interface')
        if not stash:
            logger("No Stash interface configured", "ERROR")
            return None
            
        # Use the find_studio method from StashInterface
        studio = stash.find_studio(studio_id)
        return studio
        
    except Exception as e:
        logger(f"Error finding local studio: {e}", "ERROR")
        return None

def search_parent_studio_all_endpoints(parent_name, parent_id, original_endpoint):
    """
    Search for a parent studio across all configured endpoints
    
    Args:
        parent_name (str): Name of the parent studio
        parent_id (str): ID of the parent studio from the original endpoint
        original_endpoint (str): The endpoint where this parent was originally found
        
    Returns:
        list: List of potential parent studio matches with their metadata
    """
    matches = []
    
    # Search across all configured endpoints
    for endpoint in config['stashbox_endpoints']:
        try:
            if not endpoint['api_key']:
                continue
                
            # Skip the original endpoint as we already have that data
            if endpoint['endpoint'] == original_endpoint:
                matches.append({
                    'id': parent_id,
                    'name': parent_name,
                    'endpoint': original_endpoint,
                    'endpoint_name': endpoint['name'],
                    'api_key': endpoint['api_key'],
                    'is_tpdb': endpoint['is_tpdb']
                })
                continue
                
            # Search on ThePornDB
            if endpoint['is_tpdb']:
                tpdb_results = search_tpdb_site(parent_name, endpoint['api_key'])
                if tpdb_results:
                    for result in tpdb_results:
                        matches.append({
                            'id': result['id'],
                            'name': result['name'],
                            'endpoint': endpoint['endpoint'],
                            'endpoint_name': endpoint['name'],
                            'api_key': endpoint['api_key'],
                            'is_tpdb': True,
                            'parent': result.get('parent')  # In case of nested parents
                        })
            
            # Search on StashDB or other Stash-box endpoints
            else:
                response = graphql_request(
                    STASHBOX_SEARCH_STUDIO_QUERY,
                    {'term': parent_name},
                    endpoint['endpoint'],
                    endpoint['api_key']
                )
                
                if response and 'searchStudio' in response:
                    for result in response['searchStudio']:
                        matches.append({
                            'id': result['id'],
                            'name': result['name'],
                            'endpoint': endpoint['endpoint'],
                            'endpoint_name': endpoint['name'],
                            'api_key': endpoint['api_key'],
                            'is_tpdb': False
                        })
                        
        except Exception as e:
            logger(f"Error searching {endpoint['name']} for parent studio: {e}", "ERROR")
            continue
            
    logger(f"✅ Found parent studio matches: {len(matches)} across endpoints", "INFO")
    return matches

def find_or_create_parent_studio(parent_data, original_endpoint, dry_run=False):
    """Find or create parent studio using UUID matching"""
    parent_uuid = parent_data.get('id')
    parent_name = parent_data.get('name')
    
    if not parent_uuid:
        logger(f"❌ No parent UUID provided for: {parent_name}", "INFO")
        return None
    
    # Get all studios from Stash
    studios = config.get('stash_interface').find_studios()
    
    # First, try to find existing studio by UUID
    for studio in studios:
        if studio.get('stash_ids'):
            # Check if this studio has the parent UUID
            if any(sid['endpoint'] == original_endpoint and 
                  sid['stash_id'] == parent_uuid
                  for sid in studio['stash_ids']):
                logger(f"✅ Found existing parent studio: {studio['name']} (UUID match)", "INFO")
                return studio['id']
    
    # If no existing studio found, create new one
    if not dry_run:
        try:
            # Create the parent studio with the original UUID
            parent_studio = {
                'name': parent_name,
                'url': None,
                'stash_ids': [{
                    'endpoint': original_endpoint,
                    'stash_id': parent_uuid
                }]
            }
            
            # Create the studio in Stash
            result = config.get('stash_interface').create_studio(parent_studio)
            if result:
                parent_studio_id = result.get('id')
                logger(f"✅ Created new parent studio: {parent_name} with ID: {parent_studio_id}", "INFO")
                return parent_studio_id
            else:
                logger(f"❌ Failed to create parent studio: {parent_name}", "ERROR")
                return None
        except Exception as e:
            logger(f"❌ Error creating parent studio: {str(e)}", "ERROR")
            return None
    else:
        logger(f"DRY RUN: Would create parent studio: {parent_name}", "INFO")
        return None

def add_tpdb_id_to_studio(studio_id, tpdb_id, dry_run=False):
    """Add a ThePornDB ID to a studio that already exists
    
    Args:
        studio_id (int): The Stash studio ID to update
        tpdb_id (str): The ThePornDB UUID to add
        dry_run (bool): If True, only log what would be done without making changes
    """
    global config
    stash = config.get('stash_interface')
    if not stash:
        logger("No Stash interface configured", "ERROR")
        return False
        
    try:
        # Get the studio first
        studio = stash.find_studio(studio_id)
        if not studio:
            logger(f"Studio {studio_id} not found", "ERROR")
            return False
            
        logger(f"Adding ThePornDB UUID {tpdb_id} to studio {studio_id}", "DEBUG")
        
        # Get existing stash IDs
        existing_stash_ids = studio.get('stash_ids', [])
        
        # Check if the ThePornDB UUID already exists
        if any(s.get('endpoint') == 'https://theporndb.net/graphql' and 
               s.get('stash_id') == tpdb_id for s in existing_stash_ids):
            logger(f"Studio {studio['name']} already has ThePornDB UUID {tpdb_id}", "DEBUG")
            return True
            
        # Add the ThePornDB UUID
        new_stash_id = {
            'endpoint': 'https://theporndb.net/graphql',
            'stash_id': tpdb_id  # Using UUID from TPDB
        }
        
        # Remove any existing TPDB ID
        existing_stash_ids = [s for s in existing_stash_ids if s.get('endpoint') != 'https://theporndb.net/graphql']
        existing_stash_ids.append(new_stash_id)
        
        if dry_run:
            logger(f"🔄 DRY RUN: Would add ThePornDB UUID {tpdb_id} to studio {studio['name']} (ID: {studio_id})", "INFO")
            return True
            
        # Update the studio
        studio['stash_ids'] = existing_stash_ids
        if stash.update_studio(studio):
            logger(f"🔗 Added ThePornDB UUID {tpdb_id} to studio {studio['name']} (ID: {studio_id})", "INFO")
            return True
        else:
            logger(f"Failed to update studio {studio['name']} with ThePornDB UUID", "ERROR")
            return False
            
    except Exception as e:
        logger(f"Error adding ThePornDB UUID to studio: {e}", "ERROR")
        return False

def update_studio(studio_data, local_id, dry_run=False):
    """
    Update a studio with new data
    
    Args:
        studio_data (dict): The studio data to update
        local_id (str): The ID of the studio to update
        dry_run (bool): If True, don't make any changes
        
    Returns:
        dict: Updated studio data or None if failed
    """
    logger(f"📝 Updating studio with ID: {local_id}", "INFO")
    
    try:
        # Get StashInterface from config
        stash = config.get('stash_interface')
        if not stash:
            logger("No Stash interface configured", "ERROR")
            return None
        
        # Ensure we have the local ID in the data
        studio_data['id'] = local_id
        
        if dry_run:
            logger(f"🔄 DRY RUN: Would update studio {local_id} with data: {studio_data}", "INFO")
            return studio_data
        else:
            # Use the StashInterface to update the studio
            result = stash.update_studio(studio_data)
            if result:
                logger(f"✅ Successfully updated studio {local_id}", "DEBUG")
                return result
            else:
                logger(f"❌ Failed to update studio {local_id}", "ERROR")
                return None
                
    except Exception as e:
        logger(f"Error updating studio {local_id}: {e}", "ERROR")
        return None

def process_studio_with_matches(studio, matches, dry_run=False, force=False):
    """Process a studio with pre-fetched matches"""
    if not matches:
        logger(f"No matches provided for studio {studio['name']}", "ERROR")
        return False
        
    studio_id = studio.get('id')
    studio_name = studio['name']
    
    logger(f"🔍 Processing studio: {studio_name} (ID: {studio_id})", "INFO")
    logger(f"Found {len(matches)} matches to process", "DEBUG")
    
    # Initialize variables to track all changes
    all_stash_ids = studio.get('stash_ids', []).copy()  # Keep existing stash_ids
    logger(f"Current stash_ids: {all_stash_ids}", "DEBUG")
    
    best_image = None
    best_image_score = 0  # Track how good the match is for the image
    best_tpdb_match = None
    best_tpdb_score = 0  # Track best TPDB match score
    best_stashbox_matches = {}  # Track best match per endpoint
    best_url = studio.get('url')
    best_parent_id = studio.get('parent_id')
    has_changes = False
    seen_urls = set()
    changes_summary = []
    
    if best_url:
        seen_urls.add(best_url)

    # Process each match independently to collect UUIDs from all endpoints
    for match in matches:
        try:
            logger(f"Processing match from {match.get('endpoint_name', 'Unknown')}: {match}", "DEBUG")
            
            if match.get('is_tpdb'):
                # Process TPDB match
                logger(f"Processing TPDB match with ID: {match['id']}", "DEBUG")
                studio_data = find_tpdb_site(match['id'], match['api_key'])
                if studio_data:
                    logger(f"Found TPDB studio data: {studio_data}", "DEBUG")
                    
                    # Calculate name similarity for TPDB match
                    name_similarity = fuzz.ratio(studio_name.lower(), studio_data['name'].lower())
                    logger(f"TPDB match score for {studio_data['name']}: {name_similarity}", "DEBUG")
                    
                    # Only update TPDB ID if this is a better match
                    if name_similarity > best_tpdb_score:
                        best_tpdb_score = name_similarity
                        best_tpdb_match = studio_data
                        logger(f"Found better TPDB match: {studio_data['name']} (score: {name_similarity})", "DEBUG")
                    
                    # Handle TPDB images - calculate match score for the logo
                    if studio_data.get('images'):
                        for image in studio_data['images']:
                            if image.get('url') and image['url'].startswith(('http://', 'https://')):
                                # Only update if this is a better match
                                if name_similarity > best_image_score:
                                    best_image = image['url']
                                    best_image_score = name_similarity
                                    logger(f"Found better logo match (score: {name_similarity}) from {studio_data['name']}", "DEBUG")
                                    if "logo" not in changes_summary:
                                        changes_summary.append("logo")
                                break
            else:
                # Process Stash-box match
                logger(f"Processing Stash-box match with ID: {match['id']}", "DEBUG")
                studio_data = find_stashbox_studio(match['id'], match['endpoint'], match['api_key'])
                if studio_data:
                    logger(f"Found Stash-box studio data: {studio_data}", "DEBUG")
                    
                    # Calculate name similarity for Stash-box match
                    name_similarity = fuzz.ratio(studio_name.lower(), studio_data['name'].lower())
                    logger(f"Stash-box match score for {studio_data['name']}: {name_similarity}", "DEBUG")
                    
                    # Track best match per endpoint
                    endpoint = match['endpoint']
                    if endpoint not in best_stashbox_matches or name_similarity > best_stashbox_matches[endpoint]['score']:
                        best_stashbox_matches[endpoint] = {
                            'data': studio_data,
                            'score': name_similarity,
                            'endpoint_name': match['endpoint_name']
                        }
                        logger(f"Found better {match['endpoint_name']} match: {studio_data['name']} (score: {name_similarity})", "DEBUG")
                    
                    # Handle Stash-box images - calculate match score for the logo
                    if studio_data.get('images'):
                        for image in studio_data['images']:
                            if image.get('url') and image['url'].startswith(('http://', 'https://')):
                                # Only update if this is a better match
                                if name_similarity > best_image_score:
                                    best_image = image['url']
                                    best_image_score = name_similarity
                                    logger(f"Found better logo match (score: {name_similarity}) from {studio_data['name']}", "DEBUG")
                                    if "logo" not in changes_summary:
                                        changes_summary.append("logo")
                                break
                    
                    # Handle URLs if available
                    if studio_data.get('urls'):
                        for url_data in studio_data['urls']:
                            url = url_data.get('url')
                            if url and url not in seen_urls and url.startswith(('http://', 'https://')):
                                best_url = url
                                seen_urls.add(url)
                                changes_summary.append("URL")
                                break
        except Exception as e:
            logger(f"❌ Error processing match from {match.get('endpoint_name', 'Unknown')}: {str(e)}", "ERROR")
            continue

    # After processing all matches, update the IDs with the best matches
    
    # Update TPDB ID if we found a good match
    if best_tpdb_match:
        all_stash_ids = update_stash_ids(all_stash_ids, best_tpdb_match['id'], 'https://theporndb.net/graphql')
        has_changes = True
        changes_summary.append("ThePornDB UUID")
        logger(f"Added/Updated ThePornDB UUID: {best_tpdb_match['id']} from best match: {best_tpdb_match['name']} (score: {best_tpdb_score})", "DEBUG")

    # Update Stash-box IDs for each endpoint's best match
    for endpoint, match_data in best_stashbox_matches.items():
        studio_data = match_data['data']
        all_stash_ids = update_stash_ids(all_stash_ids, studio_data['id'], endpoint)
        has_changes = True
        changes_summary.append(f"{match_data['endpoint_name']} UUID")
        logger(f"Added/Updated {match_data['endpoint_name']} UUID: {studio_data['id']} from best match: {studio_data['name']} (score: {match_data['score']})", "DEBUG")

    logger(f"Final stash_ids after processing: {all_stash_ids}", "DEBUG")
    
    # Perform single update with all collected changes
    if has_changes:
        if not dry_run:
            try:
                # Start with required fields
                studio_update = {
                    'id': studio_id,
                    'name': studio_name,
                }
                
                # Only include optional fields if they have valid values
                if best_url:
                    studio_update['url'] = best_url
                if best_parent_id:
                    studio_update['parent_id'] = best_parent_id
                if all_stash_ids:
                    studio_update['stash_ids'] = all_stash_ids
                
                # Only include image if we actually found one and it has a valid URL
                if best_image and isinstance(best_image, str) and best_image.startswith(('http://', 'https://')):
                    studio_update['image'] = best_image
                    logger(f"Adding image URL: {best_image}", "DEBUG")
                
                # Create a concise summary of changes
                unique_changes = list(dict.fromkeys(changes_summary))
                summary = f"📝 {studio_name}: Updated {', '.join(unique_changes)}"
                if force:
                    summary += " (forced update)"
                logger(summary, "INFO")
                
                result = update_studio(studio_update, studio_id, dry_run)
                if result:
                    logger(f"✅ Successfully updated studio {studio_name}", "INFO")
                else:
                    logger(f"❌ Failed to update studio {studio_name}", "ERROR")
                return True
            except Exception as e:
                logger(f"❌ Update failed for {studio_name}: {str(e)}", "ERROR")
                return False
        else:
            unique_changes = list(dict.fromkeys(changes_summary))
            logger(f"🔍 [DRY RUN] Would update {studio_name} with: {', '.join(unique_changes)}", "INFO")
            return True
    else:
        logger(f"ℹ️ No changes needed for {studio_name}", "DEBUG")
        return False

if __name__ == "__main__":
    main() 