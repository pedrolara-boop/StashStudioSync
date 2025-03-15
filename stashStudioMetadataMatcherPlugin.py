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
        # Read the JSON input from stdin
        if not sys.stdin.isatty():
            plugin_input = json.loads(sys.stdin.read())
            server_connection = plugin_input.get('server_connection', {})
            plugin_args = plugin_input.get('args', {})
            
            # Create a StashInterface using the server connection details
            stash = StashInterface(server_connection)
            
            # Get the Stash configuration
            stash_config = stash.get_configuration()
            
            # Get plugin settings
            plugin_settings = {}
            
            # Define the plugin ID - must match the id in the YAML file
            plugin_id = "stash_studio_metadata_matcher"
            
            try:
                # Try to get plugin settings directly using the StashInterface
                plugin_settings = stash.find_plugin_config(plugin_id)
                if plugin_settings:
                    log.info(f"🔧 Found plugin settings via StashInterface: {plugin_settings}")
                else:
                    # Fall back to checking the configuration
                    if 'plugins' in stash_config and plugin_id in stash_config['plugins']:
                        plugin_settings = stash_config['plugins'][plugin_id]
                        log.info(f"🔧 Found plugin settings in Stash configuration: {plugin_settings}")
                    elif 'plugins' in stash_config and 'StashStudioMetadataMatcher' in stash_config['plugins']:
                        # Try with the old ID for backward compatibility
                        plugin_settings = stash_config['plugins']['StashStudioMetadataMatcher']
                        log.info(f"🔧 Found plugin settings with old ID in Stash configuration: {plugin_settings}")
                    else:
                        log.info("🔧 No plugin settings found")
            except Exception as e:
                log.error(f"Error getting plugin settings: {e}")
                # Fall back to checking the configuration
                if 'plugins' in stash_config and plugin_id in stash_config['plugins']:
                    plugin_settings = stash_config['plugins'][plugin_id]
                    log.info(f"🔧 Found plugin settings in Stash configuration: {plugin_settings}")
                elif 'plugins' in stash_config and 'StashStudioMetadataMatcher' in stash_config['plugins']:
                    # Try with the old ID for backward compatibility
                    plugin_settings = stash_config['plugins']['StashStudioMetadataMatcher']
                    log.info(f"🔧 Found plugin settings with old ID in Stash configuration: {plugin_settings}")
                else:
                    log.info("🔧 No plugin settings found")
            
            # Create our config dictionary
            config = {
                'scheme': server_connection.get('Scheme', 'http'),
                'host': server_connection.get('Host', 'localhost'),
                'port': server_connection.get('Port', 9999),
                'api_key': server_connection.get('ApiKey', ''),
                'tpdb_api_key': '',
                'stashdb_api_key': '',
                'log_file': 'studio_metadata_matcher.log',
                'fuzzy_threshold': 95,  # High threshold for more precise matches in plugin mode
                'use_fuzzy_matching': True,
                'stash_interface': stash,  # Store the StashInterface in the config
                'stashbox_endpoints': []  # Will store all configured Stash-box endpoints
            }
            
            # Get API keys from Stash configuration and build the list of all Stash-box endpoints
            if 'stashBoxes' in stash_config.get('general', {}):
                for stash_box in stash_config['general']['stashBoxes']:
                    endpoint = stash_box.get('endpoint', '')
                    api_key = stash_box.get('api_key', '')
                    name = stash_box.get('name', 'Unknown')
                    
                    # Add to our list of endpoints
                    if endpoint and api_key:
                        # Determine if this is ThePornDB (which uses a different API)
                        is_tpdb = "theporndb.net" in endpoint.lower()
                        
                        config['stashbox_endpoints'].append({
                            'name': name,
                            'endpoint': endpoint,
                            'api_key': api_key,
                            'is_tpdb': is_tpdb
                        })
                        
                        # Also set the specific keys for backward compatibility
                        if is_tpdb:
                            config['tpdb_api_key'] = api_key
                        elif "stashdb.org" in endpoint.lower():
                            config['stashdb_api_key'] = api_key
            
            # Log the configuration (without sensitive data)
            log.info(f"🔧 Using Stash server: {config['scheme']}://{config['host']}:{config['port']}")
            log.info(f"🔧 Found {len(config['stashbox_endpoints'])} configured Stash-box endpoints:")
            
            # Categorize endpoints for better logging
            standard_endpoints = []
            extra_endpoints = []
            
            for endpoint in config['stashbox_endpoints']:
                if "theporndb.net" in endpoint['endpoint'].lower():
                    standard_endpoints.append(f"  - ThePornDB: {endpoint['name']} ({endpoint['endpoint']})")
                elif "stashdb.org" in endpoint['endpoint'].lower():
                    standard_endpoints.append(f"  - StashDB: {endpoint['name']} ({endpoint['endpoint']})")
                else:
                    extra_endpoints.append(f"  - {endpoint['name']} ({endpoint['endpoint']})")
            
            # Log standard endpoints first
            for endpoint_log in standard_endpoints:
                log.info(endpoint_log)
            
            # Then log extra endpoints with special highlighting
            if extra_endpoints:
                log.info(f"🌟 Found {len(extra_endpoints)} additional Stash-box endpoints:")
                for endpoint_log in extra_endpoints:
                    log.info(endpoint_log)
                log.info("🌟 Studios will be matched and updated with data from ALL endpoints above")
            else:
                log.info("ℹ️ No additional Stash-box endpoints configured beyond ThePornDB and StashDB")
            
            # Build API URLs
            local_api_url = f"{config['scheme']}://{config['host']}:{config['port']}/graphql"
            
            # Get plugin arguments
            def str_to_bool(value):
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ('true', '1', 'yes', 'on')

            dry_run = str_to_bool(plugin_args.get('dry_run', False))
            force = str_to_bool(plugin_args.get('force', False))
            studio_id = plugin_args.get('studio_id')  # New argument
            
            # Override with plugin settings if available
            if plugin_settings and 'dry_run' in plugin_settings:
                dry_run = str_to_bool(plugin_settings['dry_run'])
            
            # Make the mode setting visible in the logs at startup
            mode_str = " (FORCE)" if force else " (DRY RUN)" if dry_run else ""
            log.info(f"🚀 Starting StashStudioMetadataMatcherPlugin{mode_str} - Fuzzy threshold: {config['fuzzy_threshold']}")
            
            # Get fuzzy matching settings from plugin args if provided
            if 'fuzzy_threshold' in plugin_args:
                config['fuzzy_threshold'] = int(plugin_args['fuzzy_threshold'])
            
            if 'use_fuzzy_matching' in plugin_args:
                config['use_fuzzy_matching'] = plugin_args['use_fuzzy_matching']
            
            # Set up logging with rotation
            log_dir = os.path.dirname(os.path.abspath(__file__))
            log_path = os.path.join(log_dir, config['log_file'])
            rotating_logger = setup_rotating_logger(log_path)
            
            # Create a custom logger function that writes to both stashapi.log and our rotating log
            def custom_log(message, level="INFO"):
                # Map level string to logging level
                level_map = {
                    "INFO": logging.INFO,
                    "ERROR": logging.ERROR,
                    "DEBUG": logging.DEBUG,
                    "WARNING": logging.WARNING,
                    "CRITICAL": logging.CRITICAL
                }
                
                # Log to rotating file
                log_level = level_map.get(level, logging.INFO)
                rotating_logger.log(log_level, message)
                
                # Also print to console when running from command line
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}")
                
                # Also use the stashapi logging
                if level == "INFO":
                    log.info(message)
                elif level == "ERROR":
                    log.error(message)
                elif level == "DEBUG":
                    log.debug(message)
                elif level == "PROGRESS":
                    log.progress(float(message))
            
            # Override the logger from the main script
            globals()['logger'] = custom_log
            
            # Create new functions to handle multiple Stash-box endpoints
            def search_all_stashboxes(studio_name):
                """Search for a studio across all configured Stash-box endpoints"""
                results = []
                
                for endpoint in config['stashbox_endpoints']:
                    try:
                        if endpoint['is_tpdb']:
                            # Use ThePornDB-specific search
                            tpdb_results = search_tpdb_site(studio_name, endpoint['api_key'])
                            if tpdb_results:
                                for result in tpdb_results:
                                    results.append({
                                        'id': result['id'],
                                        'name': result['name'],
                                        'endpoint': endpoint['endpoint'],
                                        'endpoint_name': endpoint['name'],
                                        'api_key': endpoint['api_key'],
                                        'is_tpdb': True
                                    })
                        else:
                            # Use standard Stash-box search
                            response = graphql_request(
                                STASHBOX_SEARCH_STUDIO_QUERY, 
                                {'term': studio_name}, 
                                endpoint['endpoint'], 
                                endpoint['api_key']
                            )
                            
                            if response and 'searchStudio' in response:
                                for result in response['searchStudio']:
                                    results.append({
                                        'id': result['id'],
                                        'name': result['name'],
                                        'endpoint': endpoint['endpoint'],
                                        'endpoint_name': endpoint['name'],
                                        'api_key': endpoint['api_key'],
                                        'is_tpdb': False
                                    })
                    except Exception as e:
                        logger(f"Error searching {endpoint['name']}: {e}", "ERROR")
                
                return results
            
            def find_studio_in_stashbox(studio_id, endpoint_info):
                """Find a studio in a specific Stash-box endpoint"""
                try:
                    if endpoint_info['is_tpdb']:
                        # Use ThePornDB-specific find
                        return find_tpdb_site(studio_id, endpoint_info['api_key'])
                    else:
                        # Use standard Stash-box find
                        response = graphql_request(
                            STASHBOX_FIND_STUDIO_QUERY, 
                            {'id': studio_id}, 
                            endpoint_info['endpoint'], 
                            endpoint_info['api_key']
                        )
                        
                        if response and 'findStudio' in response:
                            return response['findStudio']
                except Exception as e:
                    logger(f"Error finding studio in {endpoint_info['name']}: {e}", "ERROR")
                
                return None
            
            # Override the update_studio_data function to use our new multi-endpoint functions
            original_update_studio_data = update_studio_data
            def wrapped_update_studio_data(studio, dry_run=False, force=False):
                # Initial processing message
                logger(f"🔍 Analyzing studio: '{studio['name']}' (ID: {studio['id']})", "INFO")
            
                # Check if the studio already has stash IDs
                existing_stash_ids = {}
                for stash in studio['stash_ids']:
                    existing_stash_ids[stash['endpoint']] = stash['stash_id']
                
                # Check if the studio already has a parent studio
                has_parent = studio.get('parent_studio') is not None
                
                # If force is not enabled and the studio already has all information, skip it
                if not force and has_parent and len(existing_stash_ids) >= len(config['stashbox_endpoints']):
                    logger(f"✅ Studio '{studio['name']}' is complete - no updates needed", "INFO")
                    return False
            
                # If force is enabled, log that we're forcing an update
                if force and has_parent and existing_stash_ids:
                    logger(f"🔄 Force updating studio '{studio['name']}' even though it already has some data", "INFO")
            
                # Search for matches on all Stash-box endpoints
                all_matches = []
                
                # Only search if we don't have IDs for all endpoints or force is enabled
                if force or len(existing_stash_ids) < len(config['stashbox_endpoints']):
                    try:
                        stashbox_results = search_all_stashboxes(studio['name'])
                        
                        if stashbox_results:
                            # First try exact matches
                            exact_matches = [result for result in stashbox_results if result['name'].lower() == studio['name'].lower()]
            
                            if exact_matches:
                                all_matches.extend(exact_matches)
                                logger(f"🎯 Found {len(exact_matches)} exact matches across Stash-box endpoints", "INFO")
                            
                            # If no exact match or we want more matches, try fuzzy matching if enabled
                            if config.get('use_fuzzy_matching', True) and (not exact_matches or force):
                                # Group results by endpoint to avoid comparing across different sources
                                endpoint_results = {}
                                for result in stashbox_results:
                                    if result['endpoint'] not in endpoint_results:
                                        endpoint_results[result['endpoint']] = []
                                    endpoint_results[result['endpoint']].append(result)
                                
                                # Find best fuzzy match for each endpoint
                                for endpoint, results in endpoint_results.items():
                                    fuzzy_match, score = fuzzy_match_studio_name(
                                        studio['name'], 
                                        results, 
                                        config.get('fuzzy_threshold', 95)
                                    )
                                    if fuzzy_match and fuzzy_match not in all_matches:
                                        all_matches.append(fuzzy_match)
                                        logger(f"🎯 Found fuzzy match on {fuzzy_match['endpoint_name']}: {fuzzy_match['name']} (score: {score})", "INFO")
                        else:
                            logger(f"❓ No matches found across Stash-box endpoints for: {studio['name']}", "DEBUG")
                    except Exception as e:
                        logger(f"Error searching Stash-box endpoints: {e}", "ERROR")
                
                # Get studio data from all endpoints where we have matches or existing IDs
                studio_data_by_endpoint = {}
                
                # First, get data for existing IDs
                for endpoint, stash_id in existing_stash_ids.items():
                    # Find the endpoint info
                    endpoint_info = next((e for e in config['stashbox_endpoints'] if e['endpoint'] == endpoint), None)
                    if endpoint_info:
                        try:
                            studio_data = find_studio_in_stashbox(stash_id, endpoint_info)
                            if studio_data:
                                studio_data_by_endpoint[endpoint] = studio_data
                                logger(f"Retrieved data from {endpoint_info['name']} using existing ID: {stash_id}", "DEBUG")
                        except Exception as e:
                            logger(f"Error retrieving data from {endpoint_info['name']}: {e}", "ERROR")
                
                # Then, get data for new matches
                for match in all_matches:
                    endpoint = match['endpoint']
                    # Skip if we already have data for this endpoint
                    if endpoint in studio_data_by_endpoint:
                        continue
                    
                    try:
                        studio_data = find_studio_in_stashbox(match['id'], match)
                        if studio_data:
                            studio_data_by_endpoint[endpoint] = studio_data
                            logger(f"Retrieved data from {match['endpoint_name']} using matched ID: {match['id']}", "DEBUG")
                    except Exception as e:
                        logger(f"Error retrieving data from {match['endpoint_name']}: {e}", "ERROR")
                
                # Check if we need to update anything
                need_update = force or len(studio_data_by_endpoint) > 0 or not has_parent
                
                if need_update:
                    # Combine data from all sources, with priority to certain endpoints if needed
                    combined_data = {}
                    
                    # Process data from each endpoint
                    for endpoint, data in studio_data_by_endpoint.items():
                        # Extract image URL
                        if 'images' in data and data['images']:
                            combined_data.setdefault('image', data['images'][0].get('url'))
                        
                        # Extract URL
                        if 'urls' in data and data['urls']:
                            # Find the HOME type URL if available
                            for url_obj in data['urls']:
                                if url_obj.get('type') == 'HOME':
                                    combined_data.setdefault('url', url_obj.get('url'))
                                    break
                            # If no HOME type, just use the first URL
                            if 'url' not in combined_data and data['urls']:
                                combined_data.setdefault('url', data['urls'][0].get('url'))
                        
                        # Handle parent studio
                        if 'parent' in data and data['parent']:
                            # Find the endpoint info
                            endpoint_info = next((e for e in config['stashbox_endpoints'] if e['endpoint'] == endpoint), None)
                            if endpoint_info:
                                parent_id = find_or_create_parent_studio(data['parent'], endpoint, dry_run)
                                if parent_id and 'parent_id' not in combined_data:
                                    combined_data['parent_id'] = parent_id
                                    logger(f"Found parent studio ID from {endpoint_info['name']}: {parent_id}", "DEBUG")
                    
                    # Build the new stash_ids list
                    new_stash_ids = []
                    
                    # Add existing stash IDs that are still valid
                    for stash in studio['stash_ids']:
                        # Check if we have a new match for this endpoint
                        has_new_match = False
                        for match in all_matches:
                            if match['endpoint'] == stash['endpoint'] and match['id'] != stash['stash_id']:
                                has_new_match = True
                                break
                        
                        if not has_new_match:
                            # Keep this ID
                            new_stash_ids.append(stash)
                    
                    # Add new stash IDs from matches
                    for match in all_matches:
                        # Check if we already have this ID
                        if not any(s['endpoint'] == match['endpoint'] and s['stash_id'] == match['id'] for s in new_stash_ids):
                            new_stash_ids.append({
                                'stash_id': match['id'],
                                'endpoint': match['endpoint']
                            })
                            logger(f"Adding {match['endpoint_name']} ID: {match['id']}", "DEBUG")
                    
                    # Only include fields that need to be updated
                    studio_update_data = {
                        'id': studio['id']  # Always include the ID
                    }
                    
                    # Only add fields that have values and need to be updated
                    if 'name' in combined_data:
                        studio_update_data['name'] = combined_data.get('name')
                    if 'url' in combined_data:
                        studio_update_data['url'] = combined_data.get('url')
                    if 'image' in combined_data:
                        studio_update_data['image'] = combined_data.get('image')
                    if new_stash_ids:
                        studio_update_data['stash_ids'] = new_stash_ids
                    if 'parent_id' in combined_data:
                        studio_update_data['parent_id'] = combined_data.get('parent_id')
                    
                    # When finding matches, simplify the log message
                    if exact_matches:
                        logger(f"🎯 Found match on {match['endpoint_name']}: {match['name']}", "INFO")
                    elif fuzzy_match:
                        logger(f"🎯 Found fuzzy match on {match['endpoint_name']}: {match['name']}", "INFO")
                    
                    # Build a human-readable summary of updates
                    updates = []
                    if 'name' in studio_update_data:
                        updates.append("name")
                    if 'url' in studio_update_data:
                        updates.append("URL")
                    if 'image' in studio_update_data:
                        updates.append("image")
                    if 'stash_ids' in studio_update_data:
                        updates.append("stash IDs")
                    if 'parent_id' in studio_update_data and not has_parent:
                        updates.append("parent studio")
                    
                    update_summary = ", ".join(updates)
                    if len(studio_update_data) > 1:  # More than just the ID
                        try:
                            update_result = update_studio(studio_update_data, studio['id'], dry_run)
                            if update_result:
                                if not dry_run:
                                    logger(f"✅ Successfully updated studio '{studio['name']}'", "INFO")
                                return True
                            else:
                                return False
                        except Exception as e:
                            logger(f"❌ Failed to update studio '{studio['name']}': {e}", "ERROR")
                            return False
                    else:
                        return False
                else:
                    logger(f"✅ Studio '{studio['name']}' is complete - no updates needed", "INFO")
                    return False
            
            # Override the config and local_api_url in the imported functions
            for func in [update_all_studios, update_single_studio, find_studio_by_name,
                        fuzzy_match_studio_name, graphql_request, find_local_studio, 
                        get_all_studios, search_studio, search_tpdb_site, find_studio, 
                        find_tpdb_site, find_or_create_parent_studio, add_tpdb_id_to_studio, 
                        update_studio]:
                func.__globals__['config'] = config
                func.__globals__['local_api_url'] = local_api_url
                func.__globals__['tpdb_api_url'] = TPDB_API_URL
                func.__globals__['tpdb_rest_api_url'] = TPDB_REST_API_URL
                func.__globals__['stashdb_api_url'] = STASHDB_API_URL
                func.__globals__['logger'] = custom_log
            
            # Replace the update_studio_data function with our wrapped version
            update_studio_data.__globals__['update_studio_data'] = wrapped_update_studio_data
            
            # Override the update_studio function to add extra logging for dry run mode
            original_update_studio = update_studio
            def wrapped_update_studio(studio_data, local_id, dry_run=False):
                # Move this to DEBUG level
                logger(f"🔧 update_studio called with dry_run={dry_run}", "DEBUG")
                
                if dry_run:
                    # Move detailed data to DEBUG level
                    logger(f"🔍 DRY RUN: Would update studio {local_id} with data: {studio_data}", "DEBUG")
                    return studio_data
                else:
                    # Move to DEBUG level
                    logger(f"💾 Processing update for studio {local_id}", "DEBUG")
                    return original_update_studio(studio_data, local_id, dry_run)
            
            # Replace the update_studio function with our wrapped version
            update_studio.__globals__['update_studio'] = wrapped_update_studio
            
            # Create a wrapper for graphql_request that uses StashInterface for local requests
            original_graphql_request = graphql_request
            def wrapped_graphql_request(query, variables, endpoint, api_key, retries=5):
                # If this is a local request, use the StashInterface instead
                if endpoint == local_api_url or 'localhost' in endpoint or '127.0.0.1' in endpoint or '0.0.0.0' in endpoint:
                    try:
                        logger(f"Using StashInterface for local request", "DEBUG")
                        # Use the find/update methods of StashInterface directly instead of GraphQL
                        # This is a more reliable approach
                        
                        # For findStudio query
                        if "findStudio" in query and "id" in variables:
                            studio = stash.find_studio(variables["id"])
                            if studio:
                                return {"findStudio": studio}
                            return None
                        
                        # For allStudios query
                        elif "allStudios" in query:
                            studios = stash.find_studios()
                            if studios:
                                return {"allStudios": studios}
                            return None
                        
                        # For studioUpdate mutation
                        elif "studioUpdate" in query and "input" in variables:
                            input_data = variables["input"]
                            result = stash.update_studio(input_data)
                            if result:
                                return {"studioUpdate": result}
                            return None
                        
                        # For studioCreate mutation
                        elif "studioCreate" in query and "input" in variables:
                            input_data = variables["input"]
                            result = stash.create_studio(input_data)
                            if result:
                                return {"studioCreate": result}
                            return None
                        
                        # For any other queries, fall back to the original method
                        else:
                            logger(f"Using original graphql_request for query: {query[:50]}...", "DEBUG")
                            return original_graphql_request(query, variables, endpoint, api_key, retries)
                    except Exception as e:
                        logger(f"Error using StashInterface: {e}", "ERROR")
                        # Fall back to the original method
                        return original_graphql_request(query, variables, endpoint, api_key, retries)
                else:
                    # For external APIs, use the original method
                    return original_graphql_request(query, variables, endpoint, api_key, retries)
            
            # Replace the graphql_request function with our wrapped version
            for func in [update_all_studios, update_single_studio, find_studio_by_name,
                        fuzzy_match_studio_name, find_local_studio, get_all_studios,
                        search_studio, search_tpdb_site, find_studio, find_tpdb_site,
                        find_or_create_parent_studio, add_tpdb_id_to_studio, update_studio,
                        update_studio_data]:
                func.__globals__['graphql_request'] = wrapped_graphql_request
            
            # Process single studio or all studios
            if studio_id:
                log.info(f"🔍 Running update for single studio ID: {studio_id}")
                studio = find_local_studio(studio_id)
                if studio:
                    update_studio_data(studio, dry_run, force)
                else:
                    log.error(f"❌ Studio with ID {studio_id} not found.")
            else:
                # Existing batch processing code
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
        if hasattr(e.response, 'text'):
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
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            logger(f"Error response: {e.response.text}", "DEBUG")
        return None
    except Exception as e:
        logger(f"Unexpected error in find_tpdb_site: {e}", "ERROR")
        return None

if __name__ == "__main__":
    main() 