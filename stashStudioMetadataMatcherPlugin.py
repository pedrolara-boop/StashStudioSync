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
from datetime import datetime
from stashapi.stashapp import StashInterface
import stashapi.log as log
import logging
from logging.handlers import RotatingFileHandler
from thefuzz import fuzz

# Import core functionality from the main script
from StashStudioMetadataMatcher import (
    logger, update_all_studios, update_single_studio, find_studio_by_name,
    fuzzy_match_studio_name, graphql_request, find_local_studio, get_all_studios,
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
    try:
        if not sys.stdin.isatty():
            plugin_input = json.loads(sys.stdin.read())
            server_connection = plugin_input.get('server_connection', {})
            plugin_args = plugin_input.get('args', {})
            
            # Create a StashInterface using the server connection details
            stash = StashInterface(server_connection)
            stash_config = stash.get_configuration()
            
            # Create our config dictionary
            config = {
                'scheme': server_connection.get('Scheme', 'http'),
                'host': server_connection.get('Host', 'localhost'),
                'port': server_connection.get('Port', 9999),
                'api_key': server_connection.get('ApiKey', ''),
                'tpdb_api_key': '',
                'stashdb_api_key': '',
                'log_file': 'studio_metadata_matcher.log',
                'fuzzy_threshold': 90,
                'use_fuzzy_matching': True,
                'stash_interface': stash,
                'stashbox_endpoints': []
            }
            
            # Get API keys from Stash configuration
            if 'stashBoxes' in stash_config.get('general', {}):
                for stash_box in stash_config['general']['stashBoxes']:
                    endpoint = stash_box.get('endpoint', '')
                    api_key = stash_box.get('api_key', '')
                    name = stash_box.get('name', 'Unknown')
                    
                    if endpoint and api_key:
                        is_tpdb = "theporndb.net" in endpoint.lower()
                        
                        config['stashbox_endpoints'].append({
                            'name': name,
                            'endpoint': endpoint,
                            'api_key': api_key,
                            'is_tpdb': is_tpdb
                        })
                        
                        if is_tpdb:
                            config['tpdb_api_key'] = api_key
                        elif "stashdb.org" in endpoint.lower():
                            config['stashdb_api_key'] = api_key
            
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
                    update_studio_data(studio, dry_run, force)
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
    """Enhanced fuzzy matching with clear result logging"""
    if not name or not candidates:
        return None, 0
    
    # Group matches by endpoint for clearer logging
    matches_by_endpoint = {}
    best_match = None
    best_score = 0
    
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
        
        # Update best match while processing
        if score > best_score:
            best_score = score
            best_match = candidate
    
    # Log results by endpoint
    if matches_by_endpoint:
        logger(f"🎯 Fuzzy matching results for '{name}':", "INFO")
        for endpoint, matches in matches_by_endpoint.items():
            # Sort matches by score
            sorted_matches = sorted(matches, key=lambda x: x['score'], reverse=True)
            if sorted_matches:
                logger(f"   {endpoint}:", "INFO")
                # Show top 3 matches for each endpoint
                for match in sorted_matches[:3]:
                    logger(f"      - {match['name']} (Score: {match['score']}%)", "INFO")
    
    if best_score >= threshold and best_match is not None:
        logger(f"✅ Best match: '{best_match['name']}' (Score: {best_score}%)", "INFO")
        return best_match, best_score
    else:
        logger(f"❌ No matches above threshold ({threshold}%)", "INFO")
        return None, 0

if __name__ == "__main__":
    main() 