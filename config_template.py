# Configuration template
# Copy this file to config.py and fill in your own values
config = {
    'scheme': 'http',
    'host': 'localhost',  # Your Stash server address
    'port': 9999,         # Your Stash server port
    'api_key': '',        # Your Stash API key
    'tpdb_api_key': '',   # Your ThePornDB API key
    'stashdb_api_key': '', # Your StashDB API key
    'log_file': 'studio_metadata_matcher.log',  # Log file to track progress
    'fuzzy_threshold': 85,  # Default threshold for fuzzy matching (0-100)
    'use_fuzzy_matching': True,  # Enable fuzzy matching by default
}

# You can copy this file to config.py and update with your own values
# Alternatively, you can use command line arguments to override these values:
# python StashStudioMetadataMatcher.py --host your.stash.server --port 9999 --api-key your_api_key 