#!/usr/bin/env python3
"""
StudioSync

A plugin for matching studios in Stashapp database with ThePornDB and StashDB.

GitHub: https://github.com/pedrolara-boop/StudioSync
License: MIT
"""

import json
import sys
import os
import importlib.util
import requests
from datetime import datetime, timedelta
import time
from stashapi.stashapp import StashInterface
import stashapi.log as log
import logging
from logging.handlers import RotatingFileHandler
from thefuzz import fuzz
import argparse

# Constants for API endpoints
TPDB_API_URL = "https://theporndb.net/graphql"
TPDB_REST_API_URL = "https://api.theporndb.net"
STASHDB_API_URL = "https://stashdb.org/graphql"

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

def setup_rotating_logger(log_path):
    """Set up a rotating logger that will create new files when the size limit is reached"""
    # Create a rotating file handler
    max_bytes = 10 * 1024 * 1024  # 10MB per file
    backup_count = 5  # Keep 5 backup files
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    # Create the rotating handler
    rotating_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    rotating_handler.setFormatter(formatter)
    
    # Create logger
    logger = logging.getLogger('StudioSync')
    logger.setLevel(logging.INFO)
    logger.addHandler(rotating_handler)
    
    return logger

def main():
    """
    Main function for the plugin version.
    Reads plugin arguments from stdin and processes studios accordingly.
    """
    global config, processed_studios
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
                'log_file': 'studio_metadata_matcher.log',
                'fuzzy_threshold': 90,
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
            log.info(f"🚀 Starting StudioSync{mode_str} - Fuzzy threshold: {config['fuzzy_threshold']}")
            
            # Process single studio or all studios
            if studio_id:
                log.info(f"🔍 Running update for single studio ID: {studio_id}")
                studio = find_local_studio(studio_id)
                if studio:
                    wrapped_update_studio_data(studio, dry_run, force)
                else:
                    log.error(f"❌ Studio with ID {studio_id} not found.")
            else:
                log.info("🔄 Running update for all studios")
                update_all_studios(dry_run, force)
            
            log.info("✅ StudioSync completed")
        else:
            print("No input received from stdin. This script is meant to be run as a Stash plugin.")
    except json.JSONDecodeError:
        print("Failed to decode JSON input. This script is meant to be run as a Stash plugin.")
    except Exception as e:
        print(f"Error in StudioSync: {str(e)}")

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
        'limit': 100,  # Get more results to improve matching chances
        'sort': 'name',  # Sort by name for better matching
        'status': 'active',  # Only get active sites
        'include': 'parent,network',  # Include parent and network data in response
        'order': 'desc',  # Most relevant first
        'date_updated': 'last_month'  # Prioritize recently updated sites
    }
    
    try:
        # Add timeout to prevent hanging
        logger(f"Making request to {url} with query: {term}", "DEBUG")
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        # Log the actual URL being called (for debugging)
        logger(f"Full URL with params: {response.url}", "DEBUG")
        
        response.raise_for_status()
        data = response.json()
        
        if 'data' in data:
            sites = data['data']
            logger(f"Found {len(sites)} results for '{term}' on ThePornDB REST API", "DEBUG")
            
            # Convert to the same format as our GraphQL results
            results = []
            for site in sites:
                # Only include if we have a valid UUID
                if site.get('uuid'):
                    # Include parent and network info if available
                    parent_info = None
                    if site.get('parent') and site['parent'].get('uuid'):
                        parent_info = {
                            'id': str(site['parent']['uuid']),
                            'name': site['parent'].get('name')
                        }
                    elif site.get('network') and site['network'].get('uuid'):
                        parent_info = {
                            'id': str(site['network']['uuid']),
                            'name': site['network'].get('name')
                        }
                    
                    results.append({
                        'id': str(site.get('uuid')),
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
        # Log more details about the error
        if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'text'):
            logger(f"Error response: {e.response.text}", "DEBUG")
        return []
    except Exception as e:
        logger(f"Unexpected error in search_tpdb_site: {e}", "ERROR")
        return []

def find_tpdb_site(site_id, api_key):
    """Find a site on ThePornDB using the REST API"""
    logger(f"Finding site with ID {site_id} on ThePornDB REST API", "DEBUG")
    
    url = f"{TPDB_REST_API_URL}/sites/{site_id}"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }
    params = {
        'include': 'parent,network'  # Include parent and network data in response
    }
    
    try:
        # Add timeout to prevent hanging
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        
        # Log the raw response for debugging
        logger(f"Raw ThePornDB response: {response_data}", "DEBUG")
        
        # The API returns data wrapped in a 'data' object
        if 'data' in response_data:
            site = response_data['data']
            logger(f"Retrieved raw site data from ThePornDB REST API: {site}", "DEBUG")
            
            # Convert to the same format as our GraphQL results
            parent = None
            # Check for parent or network info in the included data
            if site.get('parent') and site['parent'].get('uuid'):
                parent = {
                    'id': str(site['parent']['uuid']),
                    'name': site['parent'].get('name')
                }
            elif site.get('network') and site['network'].get('uuid'):
                parent = {
                    'id': str(site['network']['uuid']),
                    'name': site['network'].get('name')
                }
            
            # Build the result in the same format as StashDB
            result = {
                'id': str(site.get('uuid')),
                'name': site.get('name'),
                'urls': [],
                'parent': parent,
                'images': [],
                'date_updated': site.get('updated_at')
            }
            
            # Add URL if available
            if site.get('url'):
                result['urls'].append({
                    'url': site.get('url'),
                    'type': 'HOME'
                })
            
            # Add images in priority order
            for image_field in ['poster', 'logo', 'image', 'background']:
                if site.get(image_field):
                    result['images'].append({
                        'url': site.get(image_field)
                    })
            
            logger(f"Processed site data from ThePornDB REST API: {result}", "DEBUG")
            return result
        
        logger(f"No data found in ThePornDB REST API response for site ID {site_id}", "ERROR")
        return None
    except requests.exceptions.RequestException as e:
        logger(f"ThePornDB REST API request failed: {e}", "ERROR")
        if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'text'):
            logger(f"Error response: {e.response.text}", "DEBUG")
        return None
    except Exception as e:
        logger(f"Unexpected error in find_tpdb_site: {e}", "ERROR")
        return None

def fuzzy_match_studio_name(name, candidates, threshold=85):
    """Enhanced fuzzy matching with clear result logging and endpoint tracking"""
    if not name or not candidates:
        logger("No name or candidates provided for fuzzy matching", "DEBUG")
        return None, 0, []
    
    # Group matches by endpoint for clearer logging
    matches_by_endpoint = {}
    best_matches = []  # Store best matches from each endpoint
    overall_best_match = None
    overall_best_score = 0
    
    for candidate in candidates:
        endpoint_name = candidate.get('endpoint_name', 'Unknown')
        score = fuzz.token_sort_ratio(name.lower(), candidate['name'].lower())
        
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
    
    # Log results by endpoint
    logger(f"🎯 Fuzzy matching results for '{name}':", "INFO")
    for endpoint, matches in matches_by_endpoint.items():
        if isinstance(matches, list):  # Skip our _best_score and _best_match entries
            # Sort matches by score
            sorted_matches = sorted(matches, key=lambda x: x['score'], reverse=True)
            if sorted_matches:
                logger(f"   {endpoint}:", "INFO")
                # Show top 3 matches for each endpoint
                for match in sorted_matches[:3]:
                    match_type = "EXACT" if match['score'] == 100 else "FUZZY"
                    logger(f"      - {match['name']} ({match_type} Score: {match['score']}%)", "INFO")
                
                # If this endpoint had a match above threshold, add it to best matches
                best_for_endpoint = matches_by_endpoint.get(f"{endpoint}_best_match")
                if best_for_endpoint:
                    best_matches.append(best_for_endpoint)
    
    if overall_best_match is not None and overall_best_score >= threshold:
        logger(f"✅ Best overall match: '{overall_best_match['name']}' from {overall_best_match['endpoint_name']} (Score: {overall_best_score}%)", "INFO")
        # Return both the overall best match and all matches above threshold
        return overall_best_match, overall_best_score, best_matches
    else:
        logger(f"❌ No matches above threshold ({threshold}%)", "INFO")
        return None, 0, []

def search_all_stashboxes(studio_name):
    """Search for a studio across all configured Stash-box endpoints"""
    global config
    results = []
    matches_by_endpoint = {}
    
    for endpoint in config['stashbox_endpoints']:
        try:
            if not endpoint['api_key']:
                continue
                
            if endpoint['is_tpdb']:
                # TPDB search logic (already working correctly)
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
                    
                    # Add logging to debug response from each endpoint
                    logger(f"Response from {endpoint['name']}: {response}", "DEBUG")
                    
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
                                
                                # Log each match found
                                logger(f"Found match in {endpoint['name']}: {result['name']}", "DEBUG")
                except Exception as e:
                    logger(f"Error searching {endpoint['name']}: {str(e)}", "ERROR")
                    continue
                
        except Exception as e:
            logger(f"❌ {endpoint['name']} error: {str(e)}", "ERROR")
            continue
    
    # After gathering all results, perform fuzzy matching
    if results:
        best_match, score, all_matches = fuzzy_match_studio_name(studio_name, results)
        
        # Create a concise summary of matches
        summary_lines = []
        
        # Log matches by endpoint with scores
        for endpoint_name, matches in matches_by_endpoint.items():
            if matches:
                summary_lines.append(f"\n{endpoint_name}:")
                for match in matches:
                    match_score = fuzz.token_sort_ratio(studio_name.lower(), match['name'].lower())
                    match_type = "EXACT" if match_score == 100 else "FUZZY"
                    summary_lines.append(f"- {match['name']} ({match_type} Score: {match_score}%)")
        
        # Log the summary
        if summary_lines:
            logger(f"🎯 Matches for '{studio_name}':{' '.join(summary_lines)}", "INFO")
        
        # Log best match if found
        if best_match:
            logger(f"✅ Best match: '{best_match['name']}' from {best_match['endpoint_name']} (Score: {score}%)", "INFO")
            
        return all_matches if all_matches else []
    else:
        logger(f"❌ No matches for '{studio_name}'", "INFO")
        return []

def wrapped_update_studio_data(studio, dry_run=False, force=False):
    """Update studio data with matches from all configured endpoints"""
    global config, processed_studios
    
    studio_id = studio.get('id')
    studio_name = studio['name']
    
    # Check if we've already processed this studio in this session
    if studio_id in processed_studios:
        logger(f"⚠️ Skipping already processed studio: {studio_name}", "DEBUG")
        return
        
    processed_studios.add(studio_id)  # Mark this studio as processed
    
    # Initialize variables to track all changes
    all_stash_ids = studio.get('stash_ids', []).copy()
    best_image = None  # Changed: Initialize as None instead of getting existing image_path
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
        return
    
    # First pass: Process StashDB matches to get priority images
    for match in matches:
        if not match['is_tpdb'] and match['endpoint'] == 'https://stashdb.org/graphql':
            try:
                response = graphql_request(STASHBOX_FIND_STUDIO_QUERY, {'id': match['id']}, match['endpoint'], match['api_key'])
                if response and 'findStudio' in response:
                    studio_data = response['findStudio']
                    
                    if studio_data and studio_data.get('images') and (not best_image or force):
                        # Try to find logo or poster in StashDB images
                        logo_image = next((img['url'] for img in studio_data['images'] if 'logo' in img.get('url', '').lower()), None)
                        poster_image = next((img['url'] for img in studio_data['images'] if 'poster' in img.get('url', '').lower()), None)
                        
                        if logo_image:
                            best_image = logo_image
                            has_changes = True
                            changes_summary.append("StashDB logo image")
                        elif poster_image:
                            best_image = poster_image
                            has_changes = True
                            changes_summary.append("StashDB poster image")
                        elif studio_data['images']:
                            best_image = studio_data['images'][0].get('url')
                            has_changes = True
                            changes_summary.append("StashDB image")
                    
                    # Process URLs from StashDB
                    if studio_data.get('urls'):
                        for url_data in studio_data['urls']:
                            if url_data.get('type') == 'HOME' and url_data.get('url'):
                                url = url_data['url']
                                if url not in seen_urls:
                                    if not best_url or force:
                                        best_url = url
                                        has_changes = True
                                        changes_summary.append("StashDB URL")
                                    seen_urls.add(url)
                                    break
            except Exception as e:
                logger(f"❌ StashDB error for {studio_name}: {str(e)}", "ERROR")
                continue
    
    # Second pass: Process remaining matches (ThePornDB and other stash boxes)
    for match in matches:
        endpoint = match['endpoint']
        endpoint_name = match['endpoint_name']
        
        try:
            # Get full studio data
            if match['is_tpdb']:
                studio_data = find_tpdb_site(match['id'], match['api_key'])
            else:
                # Use the same query for all Stash-box endpoints
                response = graphql_request(
                    STASHBOX_FIND_STUDIO_QUERY,
                    {'id': match['id']},
                    endpoint,
                    match['api_key']
                )
                studio_data = response.get('findStudio') if response else None
            
            if not studio_data:
                continue

            # Log data received from each endpoint
            logger(f"Received data from {endpoint_name}: {studio_data}", "DEBUG")
            
            # Update stash ID
            stash_id = {
                'endpoint': endpoint,
                'stash_id': studio_data['id']
            }
            
            # Remove existing ID for this endpoint if it exists
            all_stash_ids = [sid for sid in all_stash_ids if sid['endpoint'] != endpoint]
            all_stash_ids.append(stash_id)
            has_changes = True
            changes_summary.append(f"{endpoint_name} ID")
            
            # Update URL if available and not seen before
            if studio_data.get('urls'):
                for url_data in studio_data['urls']:
                    if url_data.get('type') == 'HOME' and url_data.get('url'):
                        url = url_data['url']
                        if url not in seen_urls:
                            if not best_url or force:
                                best_url = url
                                has_changes = True
                                changes_summary.append(f"{endpoint_name} URL")
                            seen_urls.add(url)
                            break

            # Update image only if we don't have one from StashDB and there are actual images
            if studio_data.get('images') and isinstance(studio_data['images'], list) and len(studio_data['images']) > 0 and (not best_image or force):
                # Try to find logo or poster in images, ensuring URLs are valid
                logo_image = next((
                    img['url'] 
                    for img in studio_data['images'] 
                    if img.get('url') and isinstance(img['url'], str) 
                    and img['url'].startswith(('http://', 'https://'))
                    and 'logo' in img['url'].lower()
                ), None)
                
                poster_image = next((
                    img['url'] 
                    for img in studio_data['images'] 
                    if img.get('url') and isinstance(img['url'], str)
                    and img['url'].startswith(('http://', 'https://'))
                    and 'poster' in img['url'].lower()
                ), None)
                
                if logo_image:
                    best_image = logo_image
                    has_changes = True
                    changes_summary.append(f"{endpoint_name} logo image")
                elif poster_image:
                    best_image = poster_image
                    has_changes = True
                    changes_summary.append(f"{endpoint_name} poster image")
                elif studio_data['images'][0].get('url') and isinstance(studio_data['images'][0]['url'], str) and studio_data['images'][0]['url'].startswith(('http://', 'https://')):
                    best_image = studio_data['images'][0]['url']
                    has_changes = True
                    changes_summary.append(f"{endpoint_name} image")
                else:
                    logger(f"No valid image URLs found in {endpoint_name} response", "DEBUG")

            # Process parent studio
            if studio_data.get('parent') and (not best_parent_id or force):
                parent_data = studio_data['parent']
                if not dry_run:
                    try:
                        parent_info = {
                            'id': parent_data.get('id'),
                            'name': parent_data.get('name'),
                            'url': None,
                            'image_path': None
                        }
                        parent_studio_id = find_or_create_parent_studio(parent_info, endpoint, dry_run)
                        if parent_studio_id:  # Just check if we got an ID back
                            best_parent_id = parent_studio_id
                            has_changes = True
                            changes_summary.append(f"Parent from {endpoint_name}")
                            logger(f"🔗 Linking parent studio {parent_data.get('name')} to {studio_name}", "INFO")
                    except Exception as e:
                        logger(f"❌ Parent studio error for {studio_name}: {str(e)}", "ERROR")

        except Exception as e:
            logger(f"❌ {endpoint_name} error for {studio_name}: {str(e)}", "ERROR")
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
                    logger(f"Including image URL in update: {best_image}", "DEBUG")
                else:
                    logger(f"No valid image URL found for {studio_name}, skipping image update", "DEBUG")
                
                # Log the final update data
                logger(f"Studio update data: {studio_update}", "DEBUG")
                
                # Create a concise summary of changes
                unique_changes = list(dict.fromkeys(changes_summary))
                summary = f"📝 {studio_name}: Updated {', '.join(unique_changes)}"
                if force:
                    summary += " (forced update)"
                logger(summary, "INFO")
                
                update_studio(studio_update, studio_id, dry_run)
            except Exception as e:
                logger(f"❌ Update failed for {studio_name}: {str(e)}", "ERROR")
        else:
            unique_changes = list(dict.fromkeys(changes_summary))  # Remove duplicates while preserving order
            logger(f"🔍 [DRY RUN] Would update {studio_name} with: {', '.join(unique_changes)}", "INFO")
    else:
        logger(f"ℹ️ No changes needed for {studio_name}", "DEBUG")

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
        studios = stash.find_studios()
        logger(f"Found {len(studios)} studios in Stash", "INFO")
        return studios
    except Exception as e:
        logger(f"Error getting studios: {e}", "ERROR")
        return []

def update_all_studios(dry_run=False, force=False):
    """Update all studios with metadata from configured endpoints"""
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
        has_tpdb_id = any(stash['endpoint'] == 'https://theporndb.net/graphql' for stash in studio.get('stash_ids', []))
        has_stashdb_id = any(stash['endpoint'] == 'https://stashdb.org/graphql' for stash in studio.get('stash_ids', []))
        has_parent = studio.get('parent_studio') is not None
        
        # If force is enabled, always update the studio
        # Otherwise, only update if it's missing information
        if force or not (has_tpdb_id and has_stashdb_id and has_parent):
            was_updated = wrapped_update_studio_data(studio, dry_run, force)
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
    """
    Enhanced version that searches across all endpoints
    """
    if not parent_data:
        return None
    
    parent_id = parent_data.get('id')
    parent_name = parent_data.get('name')
    
    if not parent_id or not parent_name:
        return None
    
    logger(f"🔍 Searching for parent studio: {parent_name}", "INFO")
    
    try:
        stash = config.get('stash_interface')
        if not stash:
            logger("No Stash interface configured", "ERROR")
            return None
        
        # Get all studios
        studios = stash.find_studios()
        if not studios:
            studios = []
        
        # Search across all endpoints
        parent_matches = search_parent_studio_all_endpoints(parent_name, parent_id, original_endpoint)
        
        # First, try to find existing studio by any of the matched IDs
        for studio in studios:
            if studio.get('stash_ids'):
                for match in parent_matches:
                    if any(sid['endpoint'] == match['endpoint'] and 
                          sid['stash_id'] == match['id'] 
                          for sid in studio['stash_ids']):
                        logger(f"✅ Found existing parent studio: {studio['name']}", "INFO")
                        
                        # Update studio with any missing IDs from other endpoints
                        if not dry_run:
                            existing_stash_ids = studio.get('stash_ids', []).copy()
                            updated = False
                            
                            for other_match in parent_matches:
                                if not any(sid['endpoint'] == other_match['endpoint'] and 
                                         sid['stash_id'] == other_match['id'] 
                                         for sid in existing_stash_ids):
                                    existing_stash_ids.append({
                                        'stash_id': other_match['id'],
                                        'endpoint': other_match['endpoint']
                                    })
                                    updated = True
                            
                            if updated:
                                try:
                                    stash.update_studio({
                                        'id': studio['id'],
                                        'stash_ids': existing_stash_ids
                                    })
                                    logger(f"📝 Updated parent studio {studio['name']} with {len(existing_stash_ids)} additional IDs", "INFO")
                                except Exception as e:
                                    logger(f"Error updating parent studio IDs: {e}", "ERROR")
                        
                        return studio['id']
        
        # If not found by ID, try exact name match
        for studio in studios:
            if studio['name'].lower() == parent_name.lower():
                logger(f"✅ Found existing parent studio: {studio['name']}", "INFO")
                
                if not dry_run:
                    # Add all matched IDs to the studio
                    existing_stash_ids = studio.get('stash_ids', []).copy()
                    updated = False
                    
                    for match in parent_matches:
                        if not any(sid['endpoint'] == match['endpoint'] and 
                                 sid['stash_id'] == match['id'] 
                                 for sid in existing_stash_ids):
                            existing_stash_ids.append({
                                'stash_id': match['id'],
                                'endpoint': match['endpoint']
                            })
                            updated = True
                    
                    if updated:
                        try:
                            stash.update_studio({
                                'id': studio['id'],
                                'stash_ids': existing_stash_ids
                            })
                            logger(f"📝 Updated parent studio {studio['name']} with {len(existing_stash_ids)} additional IDs", "INFO")
                        except Exception as e:
                            logger(f"Error updating parent studio IDs: {e}", "ERROR")
                
                return studio['id']
        
        # If not found, create new parent studio with all matched IDs
        if dry_run:
            logger(f"🔄 DRY RUN: Would create parent studio: {parent_name} with IDs from multiple sources", "INFO")
            return "dry-run-parent-id"
        else:
            try:
                # Get full studio data from each endpoint to find images
                best_image = None
                for match in parent_matches:
                    try:
                        if match['is_tpdb']:
                            studio_data = find_tpdb_site(match['id'], match['api_key'])
                        else:
                            response = graphql_request(
                                STASHBOX_FIND_STUDIO_QUERY,
                                {'id': match['id']},
                                match['endpoint'],
                                match['api_key']
                            )
                            studio_data = response.get('findStudio') if response else None

                        if studio_data and studio_data.get('images'):
                            # Try to find logo or poster
                            logo_image = next((img['url'] for img in studio_data['images'] 
                                            if 'logo' in img.get('url', '').lower()), None)
                            poster_image = next((img['url'] for img in studio_data['images'] 
                                              if 'poster' in img.get('url', '').lower()), None)
                            
                            if logo_image and not best_image:
                                best_image = logo_image
                            elif poster_image and not best_image:
                                best_image = poster_image
                            elif studio_data['images'] and not best_image:
                                best_image = studio_data['images'][0].get('url')
                    except Exception as e:
                        logger(f"Error getting images for parent studio from {match['endpoint_name']}: {e}", "DEBUG")
                        continue

                stash_ids = [{
                    'stash_id': match['id'],
                    'endpoint': match['endpoint']
                } for match in parent_matches]
                
                new_studio = {
                    'name': parent_name,
                    'stash_ids': stash_ids
                }
                
                if best_image:
                    new_studio['image'] = best_image
                    logger(f"📸 Adding image to parent studio {parent_name}", "INFO")

                result = stash.create_studio(new_studio)
                if result:
                    logger(f"➕ Created parent studio: {parent_name} with IDs from {len(stash_ids)} sources", "INFO")
                    return result['id']
            except Exception as e:
                logger(f"Error creating parent studio: {e}", "ERROR")
        
        return None
        
    except Exception as e:
        logger(f"Error in find_or_create_parent_studio: {e}", "ERROR")
        return None

def add_tpdb_id_to_studio(studio_id, tpdb_id, dry_run=False):
    """
    Add a ThePornDB ID to a studio that already exists
    
    Args:
        studio_id (str): The ID of the studio to update
        tpdb_id (str): The ThePornDB ID to add
        dry_run (bool): If True, don't make any changes
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger(f"Adding ThePornDB ID {tpdb_id} to studio {studio_id}", "DEBUG")
    
    try:
        # Get StashInterface from config
        stash = config.get('stash_interface')
        if not stash:
            logger("No Stash interface configured", "ERROR")
            return False
        
        # Get current studio data
        studio = stash.find_studio(studio_id)
        if not studio:
            logger(f"Could not find studio with ID {studio_id}", "ERROR")
            return False
        
        # Get existing stash_ids
        existing_stash_ids = studio.get('stash_ids', []).copy()
        
        # Check if the ThePornDB ID already exists
        if any(s.get('endpoint') == 'https://theporndb.net/graphql' and 
               s.get('stash_id') == tpdb_id for s in existing_stash_ids):
            logger(f"Studio {studio['name']} already has ThePornDB ID {tpdb_id}", "DEBUG")
            return True
        
        # Add the ThePornDB ID
        existing_stash_ids.append({
            'stash_id': tpdb_id,
            'endpoint': 'https://theporndb.net/graphql'
        })
        
        if dry_run:
            logger(f"🔄 DRY RUN: Would add ThePornDB ID {tpdb_id} to studio {studio['name']} (ID: {studio_id})", "INFO")
            return True
        else:
            try:
                # Update the studio with new stash_ids
                update_data = {
                    'id': studio_id,
                    'stash_ids': existing_stash_ids
                }
                
                result = stash.update_studio(update_data)
                if result:
                    logger(f"🔗 Added ThePornDB ID {tpdb_id} to studio {studio['name']} (ID: {studio_id})", "INFO")
                    return True
                else:
                    logger(f"Failed to update studio {studio['name']} with ThePornDB ID", "ERROR")
                    return False
                    
            except Exception as e:
                logger(f"Error adding ThePornDB ID to studio: {e}", "ERROR")
                return False
                
    except Exception as e:
        logger(f"Error in add_tpdb_id_to_studio: {e}", "ERROR")
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

if __name__ == "__main__":
    main() 