#!/usr/bin/env python3
"""
StashStudioMetadataMatcherPlugin

A plugin for matching studios in Stashapp database with ThePornDB and StashDB.

GitHub: https://github.com/pedrolara-boop/StashStudioMetadataMatcher
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

# Import core functionality from the main script
from StashStudioMetadataMatcher import (
    logger, update_single_studio, find_studio_by_name,
    find_local_studio, get_all_studios,
    search_studio, search_tpdb_site, find_studio, find_tpdb_site,
    find_or_create_parent_studio, add_tpdb_id_to_studio, update_studio,
    update_studio_data
)

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

config = {}  # Initialize empty config dictionary
processed_studios = set()  # Track which studios we've already processed

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
    logger = logging.getLogger('StashStudioMetadataMatcher')
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
            log.info(f"🚀 Starting StashStudioMetadataMatcherPlugin{mode_str} - Fuzzy threshold: {config['fuzzy_threshold']}")
            
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
            
            log.info("✅ StashStudioMetadataMatcherPlugin completed")
        else:
            print("No input received from stdin. This script is meant to be run as a Stash plugin.")
    except json.JSONDecodeError:
        print("Failed to decode JSON input. This script is meant to be run as a Stash plugin.")
    except Exception as e:
        print(f"Error in StashStudioMetadataMatcherPlugin: {str(e)}")

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
    
    logger(f"🔍 Searching for studio: {studio_name!r}", "INFO")
    
    for endpoint in config['stashbox_endpoints']:
        try:
            if not endpoint['api_key']:
                logger(f"⚠️ Skipping {endpoint['name']} - No API key", "INFO")
                continue
                
            logger(f"📌 Searching {endpoint['name']} ({endpoint['endpoint']})", "INFO")
            
            if endpoint['is_tpdb']:
                # TPDB uses its own REST API search
                tpdb_results = search_tpdb_site(studio_name, endpoint['api_key'])
                if tpdb_results:
                    for result in tpdb_results:
                        results.append({
                            'id': result['id'],
                            'name': result['name'],
                            'endpoint': endpoint['endpoint'],
                            'endpoint_name': endpoint['name'],
                            'api_key': endpoint['api_key'],
                            'is_tpdb': True,
                            'parent': result.get('parent')
                        })
            else:
                # Standard Stash-box GraphQL search for all other endpoints
                try:
                    logger(f"Making GraphQL request to {endpoint['endpoint']} for {studio_name!r}", "INFO")
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
                                results.append({
                                    'id': result['id'],
                                    'name': result['name'],
                                    'endpoint': endpoint['endpoint'],
                                    'endpoint_name': endpoint['name'],
                                    'api_key': endpoint['api_key'],
                                    'is_tpdb': False,
                                    'parent': result.get('parent')
                                })
                except Exception as e:
                    logger(f"GraphQL error for {endpoint['name']}: {str(e)}", "ERROR")
            
            # Log results for this endpoint
            endpoint_results = [r for r in results if r['endpoint'] == endpoint['endpoint']]
            if endpoint_results:
                logger(f"✨ Found {len(endpoint_results)} results on {endpoint['name']}", "INFO")
                for result in endpoint_results:
                    logger(f"   - {result['name']} (ID: {result['id']})", "INFO")
            else:
                logger(f"❌ No results found on {endpoint['name']}", "INFO")
                
        except Exception as e:
            logger(f"Error searching {endpoint['name']}: {e}", "ERROR")
            continue
    
    # After gathering all results, perform fuzzy matching
    if results:
        logger(f"🎯 Running fuzzy matching on {len(results)} total results", "INFO")
        best_match, score, all_matches = fuzzy_match_studio_name(studio_name, results)
        
        # Log matches by endpoint
        if all_matches:
            logger("🎯 Matches found from different endpoints:", "INFO")
            matches_by_endpoint = {}
            for match in all_matches:
                endpoint = match['endpoint_name']
                if endpoint not in matches_by_endpoint:
                    matches_by_endpoint[endpoint] = []
                matches_by_endpoint[endpoint].append(match)
            
            for endpoint, matches in matches_by_endpoint.items():
                logger(f"   {endpoint}:", "INFO")
                for match in matches:
                    logger(f"      - {match['name']} (ID: {match['id']})", "INFO")
        
        if best_match:
            logger(f"✅ Best overall match: {best_match['name']} from {best_match['endpoint_name']} (Score: {score}%)", "INFO")
            
        return all_matches if all_matches else []
    else:
        logger(f"❌ No matches found across any endpoints for {studio_name!r}", "INFO")
        return []

def wrapped_update_studio_data(studio, dry_run=False, force=False):
    """Update studio data with matches from all configured endpoints"""
    global config, processed_studios
    
    studio_id = studio.get('id')
    
    # Check if we've already processed this studio in this session
    if studio_id in processed_studios:
        logger(f"⚠️ Studio {studio['name']} (ID: {studio_id}) already processed in this session, skipping", "INFO")
        return
        
    processed_studios.add(studio_id)  # Mark this studio as processed
    
    logger(f"🔄 Processing studio: {studio['name']}", "INFO")
    
    # Initialize variables to track all changes
    all_stash_ids = studio.get('stash_ids', []).copy()
    best_image = studio.get('image_path')
    best_url = studio.get('url')
    best_parent_id = studio.get('parent_id')
    has_changes = False

    # Search for matches across all endpoints
    matches = search_all_stashboxes(studio['name'])
    
    if not matches:
        logger(f"❌ No matches found for studio: {studio['name']}", "INFO")
        return
    
    # Process all matches first to collect best data
    for match in matches:
        endpoint = match['endpoint']
        endpoint_name = match['endpoint_name']
        
        try:
            # Get full studio data
            if match['is_tpdb']:
                studio_data = find_tpdb_site(match['id'], match['api_key'])
            else:
                response = graphql_request(STASHBOX_FIND_STUDIO_QUERY, {'id': match['id']}, endpoint, match['api_key'])
                studio_data = response.get('findStudio') if response else None
            
            if not studio_data:
                continue

            # Update stash ID
            stash_id = {
                'endpoint': endpoint,
                'stash_id': studio_data['id']
            }
            
            # Remove existing ID for this endpoint if it exists
            all_stash_ids = [sid for sid in all_stash_ids if sid['endpoint'] != endpoint]
            all_stash_ids.append(stash_id)
            has_changes = True
            
            # Update URL if available and better than current
            if studio_data.get('urls'):
                for url_data in studio_data['urls']:
                    if url_data.get('type') == 'HOME' and url_data.get('url'):
                        if not best_url or force:
                            best_url = url_data['url']
                            has_changes = True
                            break

            # Update image with priority handling
            if studio_data.get('images') and (not best_image or force):
                logo_image = next((img['url'] for img in studio_data['images'] if 'logo' in img.get('url', '').lower()), None)
                poster_image = next((img['url'] for img in studio_data['images'] if 'poster' in img.get('url', '').lower()), None)
                
                if logo_image:
                    best_image = logo_image
                    has_changes = True
                elif poster_image and not best_image:
                    best_image = poster_image
                    has_changes = True
                elif studio_data['images'] and not best_image:
                    best_image = studio_data['images'][0].get('url')
                    has_changes = True

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
                        parent_studio = find_or_create_parent_studio(parent_info, endpoint)
                        if parent_studio and isinstance(parent_studio, dict):
                            best_parent_id = parent_studio.get('id')
                            has_changes = True
                    except Exception as e:
                        logger(f"❌ Error processing parent studio: {str(e)}", "ERROR")

        except Exception as e:
            logger(f"❌ Error processing match from {endpoint_name}: {str(e)}", "ERROR")
            continue

    # Perform single update with all collected changes
    if has_changes:
        if not dry_run:
            logger(f"💾 Updating studio {studio['name']} with new data", "INFO")
            try:
                studio_update = {
                    'id': studio_id,
                    'name': studio['name'],
                    'url': best_url,
                    'parent_id': best_parent_id,
                    'image': best_image,
                    'stash_ids': all_stash_ids
                }
                
                # Remove any None values
                studio_update = {k: v for k, v in studio_update.items() if v is not None}
                
                # Log what's being updated
                changes = []
                if all_stash_ids != studio.get('stash_ids'):
                    changes.append("stash IDs")
                if best_image != studio.get('image_path'):
                    changes.append("image")
                if best_url != studio.get('url'):
                    changes.append("URL")
                if best_parent_id != studio.get('parent_id'):
                    changes.append("parent studio")
                    
                logger(f"📝 Updating {', '.join(changes)}", "INFO")
                update_studio(studio_update, studio_id, dry_run)
                logger(f"✅ Successfully updated studio {studio['name']}", "INFO")
            except Exception as e:
                logger(f"❌ Error updating studio: {str(e)}", "ERROR")
        else:
            logger(f"🔍 [DRY RUN] Would update studio {studio['name']} with new data", "INFO")
    else:
        logger(f"ℹ️ No changes needed for studio {studio['name']}", "INFO")

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

if __name__ == "__main__":
    main() 