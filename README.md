# StashStudioMetadataMatcher

A tool for [Stashapp](https://github.com/stashapp/stash) that ensures your studios have complete metadata by:
- Adding missing ThePornDB and StashDB IDs
- Setting up proper parent-child studio relationships
- Updating basic information like URLs and images when missing

It can be used either as a Stash plugin or as a standalone Python script.

## Features

- Automatically matches your local studios with ThePornDB and StashDB
- Updates studio metadata including:
  - Parent studios (automatically creates or links parent studios)
  - URLs
  - Images
  - StashDB and ThePornDB IDs
- Can be run as a Stash plugin or standalone script
- Supports batch processing or individual studio updates(script only)
- Intelligently handles parent/child studio relationships
- Preserves existing metadata while adding new information
- Comprehensive logging with summary statistics
- Dry run mode to preview changes without applying them
- Force update option to refresh all metadata

## Requirements

- Python 3.6 or higher
- [Stash](https://github.com/stashapp/stash) instance
- API keys for Stash, ThePornDB, and StashDB

## Installation

### As a Stash Plugin

1. Download the script to your Stash plugins directory:
   ```
   cd ~/.stash/plugins
   git clone https://github.com/yourusername/StashStudioMetadataMatcher.git
   ```

   For information about the plugins directory location for your specific installation, please refer to the [official Stash documentation on adding plugins manually](https://docs.stashapp.cc/in-app-manual/plugins/#adding-plugins-manually).

2. Create your configuration file:
   ```
   cd StashStudioMetadataMatcher
   cp config_template.py config.py
   ```

3. Edit `config.py` with your API keys as shown above. This step is **crucial** - the script will not work properly without valid API keys.

4. Install the required Python dependencies:
   ```
   pip install -r requirements.txt
   ```

5. Reload plugins from the Settings page

6. The plugin should now appear in your Stash plugins list

### As a Standalone Script

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/StashStudioMetadataMatcher.git
   cd StashStudioMetadataMatcher
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create your configuration file:
   ```
   cp config_template.py config.py
   ```

4. Edit `config.py` with your own API keys and settings:
   ```python
   config = {
       'scheme': 'http',
       'host': 'localhost',  # Your Stash server address
       'port': 9999,         # Your Stash server port
       'api_key': 'YOUR_STASH_API_KEY_HERE',
       'tpdb_api_key': 'YOUR_TPDB_API_KEY_HERE',
       'stashdb_api_key': 'YOUR_STASHDB_API_KEY_HERE',
       'log_file': 'studio_metadata_matcher.log',
   }
   ```


## Usage

### As a Stash plugin

Once installed as a plugin, you can use it through the Tasks interface:

**Batch Processing via Tasks**:
- Go to Settings > Tasks
- Find "Match All Studios" in the list
- Click "Run" to process all studios in your database
- Alternatively, use "Match All Studios (Dry Run)" to preview changes without applying them
- Use "Force Update All Studios" to refresh all metadata even for complete studios


### As a standalone script

Process all studios:
```
python stashStudioMetadataMatcher.py --all
```

Process a single studio by ID:
```
python stashStudioMetadataMatcher.py --id 123
```

Process a single studio by name:
```
python stashStudioMetadataMatcher.py --name "Studio Name"
```

Limit the number of studios processed:
```
python stashStudioMetadataMatcher.py --all --limit 10
```

Preview changes without applying them (dry run):
```
python stashStudioMetadataMatcher.py --all --dry-run
```

Force update all studios (even if they already have all information):
```
python stashStudioMetadataMatcher.py --all --force
```


## Command Line Arguments

- `--all`: Process all studios in the database
- `--id ID`: Process a single studio with the specified ID
- `--name NAME`: Process a single studio by name (searches for exact match)
- `--host HOST`: Stash host (default from config)
- `--port PORT`: Stash port (default from config)
- `--scheme {http,https}`: Stash connection scheme (default from config)
- `--api-key API_KEY`: Stash API key (default from config)
- `--debug`: Enable debug mode with more verbose logging
- `--limit LIMIT`: Limit the number of studios to process when using --all
- `--dry-run`: Show what changes would be made without actually making them
- `--force`: Force update all studios even if they already have all information


## How It Works

The script works by:
1. Retrieving all studios from your Stash database
2. For each studio, searching for exact name matches on ThePornDB and StashDB
3. When a match is found, retrieving detailed information about the studio
4. Updating your local studio with the new information, including:
   - Setting the correct parent studio (creating it if necessary)
   - Adding StashDB and ThePornDB IDs
   - Updating the studio URL and image

> **Important Limitation**: The script relies on exact name matching to find studios on ThePornDB and StashDB. Studios with different names across these platforms (which is rare but does happen) will not be correctly tagged. In such cases, manual tagging may be required.

## Parent Studio Handling

One of the most powerful features of this script is its ability to properly manage parent-child studio relationships:

1. **Automatic Parent Detection**: When a studio is matched on StashDB or ThePornDB, the script checks if it has a parent studio in those databases.

2. **Parent Studio Resolution**: If a parent studio is found, the script:
   - First checks if the parent already exists in your Stash database (by StashDB/ThePornDB ID)
   - If not found by ID, it looks for an exact name match in your database
   - If found by name, it adds the external ID to the existing studio
   - If not found at all, it creates a new parent studio with the correct name and external ID

3. **Hierarchical Organization**: This ensures your studios are properly organized in the same hierarchy as on StashDB/ThePornDB, making your collection more organized and easier to browse.

4. **Priority Handling**: When both StashDB and ThePornDB have parent information, StashDB is given priority.

This feature is especially useful for large collections where manually setting up studio relationships would be time-consuming.


### Using the Script's Logging

The script provides detailed logging that helps you understand the state of your studios:

1. **Complete Studios**: Studios that already have ThePornDB IDs, StashDB IDs, and parent studios (if applicable) are marked as "complete" in the logs.

2. **Studios Needing Updates**: The script clearly indicates which studios need updates and what specific information is missing.

3. **Summary Statistics**: At the end of each run, the script provides a summary showing how many studios were updated and how many were already complete.

### Recommended Workflow

For best results, follow this workflow:

1. **Initial Scan**: Run a full scan with dry run mode first to see what changes would be made:
   ```
   python stashStudioMetadataMatcher.py --all --dry-run
   ```

2. **Apply Updates**: Run the script without dry run to apply the changes:
   ```
   python stashStudioMetadataMatcher.py --all
   ```

3. **Regular Maintenance**: Run the script periodically (e.g., weekly) to catch any new studios or updates:
   ```
   python stashStudioMetadataMatcher.py --all
   ```

4. **Force Updates**: Occasionally run with the force option to refresh all metadata:
   ```
   python stashStudioMetadataMatcher.py --all --force
   ```

5. **Check Log Files**: Review the `studio_metadata_matcher.log` file to see which studios were updated and which ones might need manual attention.

### Manual Verification

For studios that couldn't be automatically matched:

1. Use Stash's built-in studio tagger to manually search for matches
2. Check for spelling variations or alternative names
3. Consider creating custom scrapers for studios that aren't in ThePornDB or StashDB

### Tracking Progress

To help track your progress in completing studio metadata:

1. Use Stash's filtering to find studios without parent studios or external IDs
2. Create saved filters for incomplete studios to easily revisit them
3. Consider using tags to mark studios that need manual attention

## Troubleshooting

- **API Key Issues**: Ensure your API keys are correctly entered in the config.py file
- **Connection Problems**: Verify your Stash server address and port in the configuration
- **Log Files**: Check the `studio_metadata_matcher.log` file for detailed error messages
- **Permission Issues**: Make sure the script has permission to write to the log file
- **Plugin Not Appearing**: Verify that the plugin directory structure is correct and that the .yml file is properly formatted
- **Python Path Issues**: If using the plugin in Stash, make sure Python is in your system PATH

### Common Issues and Solutions

1. **Script Hangs or Times Out**:
   - The script includes timeout protection to prevent hanging
   - If it still hangs, try running with a smaller batch using the `--limit` option
   - Check your network connection to ThePornDB and StashDB

2. **No Studios Are Updated**:
   - Verify your API keys are correct
   - Check if your studios already have all the necessary information
   - Try running with the `--force` option to update even complete studios

3. **Incorrect Matches**:
   - The script only makes exact name matches to avoid errors
   - For studios with multiple exact matches, no update is made
   - Consider renaming the studio in your database to match the external source exactly

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT License](LICENSE) 