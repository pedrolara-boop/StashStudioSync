# Configuration template
# Copy this file to config.py and fill in your own values
config = {
    'scheme': 'http',
    'host': 'localhost',
    'port': 9999,
    'api_key': 'YOUR_STASH_API_KEY_HERE',  # Your Stash API key
    'tpdb_api_key': 'YOUR_TPDB_API_KEY_HERE',  # Your TPDB API key
    'stashdb_api_key': 'YOUR_STASHDB_API_KEY_HERE',  # Your stashDB API key
    'log_file': 'studio_metadata_matcher.log',  # Log file to track progress
    'fuzzy_threshold': 85,  # Threshold for fuzzy matching (0-100)
    'use_fuzzy_matching': True,  # Enable fuzzy matching by default
} 