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
  - StashDB and ThePornDB IDs (using UUIDs for ThePornDB)
- Intelligent fuzzy matching for studios with slightly different names
- Can be run as a Stash plugin or standalone script
- Supports batch processing or individual studio updates(script only)
- Intelligently handles parent/child studio relationships
- Preserves existing metadata while adding new information
- Comprehensive logging with summary statistics
- Dry run mode to preview changes without applying them
- Force update option to refresh all metadata
- Flexible configuration through environment variables or command line arguments

## Requirements

- Python 3.6 or higher
- [Stash](https://github.com/stashapp/stash) instance
- API keys for Stash, ThePornDB, and StashDB

## Installation

### As a Stash Plugin

1. Download the script to your Stash plugins directory:
   ```
   cd ~/.stash/plugins
   git clone https://github.com/pedrolara-boop/StashStudioMetadataMatcher.git
   ```

   For information about the plugins directory location for your specific installation, please refer to the [official Stash documentation on adding plugins manually](https://docs.stashapp.cc/in-app-manual/plugins/#adding-plugins-manually).

2. Install the required Python dependencies:
   ```
   cd StashStudioMetadataMatcher
   pip install -r requirements.txt
   ```

3. Reload plugins from the Settings page

4. The plugin should now appear in your Stash plugins list

> **Note**: The plugin version automatically uses your Stash API keys for ThePornDB and StashDB, so no configuration file is needed. Just make sure you have set up your Stash Boxes in the Stash settings.

### As a Standalone Script

1. Clone this repository:
   ```
   git clone https://github.com/pedrolara-boop/StashStudioMetadataMatcher.git
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
       'fuzzy_threshold': 95,  # Threshold for fuzzy matching (0-100) - higher for more precise matches
       'use_fuzzy_matching': True,  # Enable fuzzy matching by default
   }
   ```

   You can also set these values through environment variables:
   ```bash
   export STASH_HOST=your.stash.server
   export STASH_PORT=9999
   export STASH_SCHEME=http
   export STASH_API_KEY=your_api_key
   export TPDB_API_KEY=your_tpdb_key
   export STASHDB_API_KEY=your_stashdb_key
   ```

## Usage

### As a Stash plugin

Once installed as a plugin, you can use it through the Tasks interface:

**Using the Plugin Tasks**:
- Go to Settings > Plugin Tasks
- Expand the "StashStudioMetadataMatcher" section
- You'll see the following available tasks:
  - **Match All Studios**: Adds missing metadata to studios from ThePornDB and StashDB (IDs, parent studios, URLs, images)
  - **Match All Studios (Dry Run)**: Shows what changes would be made without actually making them
  - **Force Update All Studios**: Updates all studios even if they already have complete information
  - **Force Update All Studios (Dry Run)**: Shows what would be updated in force mode without making changes
- Click the corresponding "Run" button next to the task you want to execute

> **Note**: The plugin uses a high fuzzy threshold (95) by default for more precise matches. This can be adjusted when running the task.

> **Important**: The plugin automatically uses your Stash API keys for ThePornDB and StashDB, so make sure you have set up your Stash Boxes in the Stash settings.

### As a standalone script

Process all studios:
```
python stashStudioMetadataMatcher.py --all
```

Process a single studio by ID (script-only feature):
```
python stashStudioMetadataMatcher.py --id 123
```

Process a single studio by name (script-only feature):
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
- `--host HOST`: Stash host (default from config or environment)
- `--port PORT`: Stash port (default from config or environment)
- `--scheme {http,https}`: Stash connection scheme (default from config or environment)
- `--api-key API_KEY`: Stash API key (default from config or environment)
- `--debug`: Enable debug mode with more verbose logging
- `--limit LIMIT`: Limit the number of studios to process when using --all
- `--dry-run`: Show what changes would be made without actually making them
- `--force`: Force update all studios even if they already have all information
- `--fuzzy-threshold THRESHOLD`: Set the threshold for fuzzy matching (0-100, default: 85)
- `--no-fuzzy`: Disable fuzzy matching

> **Note**: Command line arguments take precedence over environment variables and config file settings.

## How It Works

The script works by:
1. Retrieving all studios from your Stash database
2. For each studio, searching for exact name matches on ThePornDB and StashDB
3. If no exact match is found, using fuzzy matching to find similar names (if enabled)
4. When a match is found, retrieving detailed information about the studio
5. Updating your local studio with the new information, including:
   - Setting the correct parent studio (creating it if necessary)
   - Adding StashDB and ThePornDB IDs (using stable UUIDs for ThePornDB)
   - Updating the studio URL and image

> **Important Note**: The script first tries exact name matching to find studios on ThePornDB and StashDB. If no exact match is found, it will use fuzzy matching (if enabled) to find similar names. This helps match studios with slight spelling differences or formatting variations.

> **ThePornDB ID Changes**: The script now uses ThePornDB's stable UUIDs instead of their numeric IDs. This ensures more reliable matching and prevents issues with ID changes. The UUIDs are unique identifiers that remain constant even if ThePornDB's internal numeric IDs change.

## Fuzzy Matching

The script includes intelligent fuzzy matching to help match studios even when names aren't exactly the same:

1. **How It Works**: Fuzzy matching compares studio names and calculates a similarity score (0-100) based on how similar they are.

2. **Threshold Control**: You can control how strict the matching is with the fuzzy threshold:
   - Higher threshold (e.g., 95): Only very similar names will match (default for plugin mode)
   - Medium threshold (85): Good balance between precision and recall (default for script mode)
   - Lower threshold (e.g., 75): More lenient matching, but may include false positives

3. **Examples of What Fuzzy Matching Can Help With**:
   - Different spacing: "StudioName" vs "Studio Name"
   - Punctuation differences: "Studio-Name" vs "Studio Name"
   - Minor spelling variations: "Brazzers" vs "Brazzers."
   - Word order differences: "Digital Playground" vs "Playground Digital"

4. **Controlling Fuzzy Matching**:
   - In the config file: Set `use_fuzzy_matching` to `True` or `False` and adjust `fuzzy_threshold`
   - Command line: Use `--no-fuzzy` to disable or `--fuzzy-threshold 90` to set a custom threshold
   - Plugin mode: Uses a high threshold (95) by default for more precise matches

5. **When to Adjust Settings**:
   - If you're getting too many incorrect matches: Increase the threshold or disable fuzzy matching
   - If you're missing matches you think should work: Lower the threshold
   - For most users, the default settings work well

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

## Troubleshooting

- **API Key Issues**: Ensure your API keys are correctly entered in the config.py file
- **Connection Problems**: Verify your Stash server address and port in the configuration
- **Log Files**: Check the `studio_metadata_matcher.log` file for detailed error messages
- **Plugin Not Appearing**: Verify that the plugin directory structure is correct and that the .yml file is properly formatted
- **Python Environment Issues**: 
  - Make sure Python 3.6+ is installed and in your system PATH
  - Verify dependencies are installed with `pip install -r requirements.txt`
  - Check the Python path in the .yml file matches your Python installation
  - For Docker installations, you may need to modify the exec path in the .yml file
  - Consider using a virtual environment if you have multiple Python versions

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

## Project Structure

The project consists of two main Python files:

1. **stashStudioMetadataMatcher.py**: The main script that can be run from the command line with various arguments. Requires a config.py file or environment variables. Supports additional features like matching by ID or name.

2. **stashStudioMetadataMatcherPlugin.py**: A specialized version optimized for use as a Stash plugin. Gets configuration directly from Stash, so no config.py file is needed. Focuses on batch processing of all studios.

This separation allows for:
- Cleaner code organization
- Optimized settings for each use case (plugin vs. command-line)
- Easier maintenance and updates
- Plugin version works without any additional configuration

Both files share the same core functionality but are optimized for their specific use cases. 