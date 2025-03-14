# Stash Studio Match Scrape

A Python script for matching studios in your [Stash](https://github.com/stashapp/stash) database with ThePornDB and StashDB. This tool helps you automatically update your studio metadata with information from these external databases.

## Features

- Automatically matches your local studios with ThePornDB and StashDB
- Updates studio metadata including:
  - Parent studios (automatically creates or links parent studios)
  - URLs
  - Images
  - StashDB and ThePornDB IDs
- Can be run as a Stash plugin or standalone script
- Supports batch processing or individual studio updates
- Intelligently handles parent/child studio relationships
- Optional automatic updates when studios are modified
- Preserves existing metadata while adding new information
- Dry run mode to preview changes without applying them

## Requirements

- Python 3.6 or higher
- [Stash](https://github.com/stashapp/stash) instance
- API keys for Stash, ThePornDB, and StashDB (optional but recommended)

## Installation

### As a Standalone Script

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/stashStudioMatchScrape.git
   cd stashStudioMatchScrape
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
       'log_file': 'studio_match_progress.log',
   }
   ```

### As a Stash Plugin

1. Download the script to your Stash plugins directory:
   ```
   cd ~/.stash/plugins
   git clone https://github.com/yourusername/stashStudioMatchScrape.git
   ```

   Note: The plugins directory location may vary depending on your Stash installation:
   - Linux: `~/.stash/plugins` or `/root/.stash/plugins`
   - macOS: `~/.stash/plugins`
   - Windows: `C:\Users\YourUsername\.stash\plugins`
   - Docker: `/root/.stash/plugins` (inside the container)

2. Create your configuration file:
   ```
   cd stashStudioMatchScrape
   cp config_template.py config.py
   ```

3. Edit `config.py` with your API keys as shown above

4. Install the required Python dependencies:
   ```
   pip install -r requirements.txt
   ```

5. Restart Stash or reload plugins from the Settings page

6. The plugin should now appear in your Stash plugins list

## Usage

### As a standalone script

Process all studios:
```
python stashStudioMatchScrape.py --all
```

Process a single studio by ID:
```
python stashStudioMatchScrape.py --id 123
```

Process a single studio by name:
```
python stashStudioMatchScrape.py --name "Studio Name"
```

Limit the number of studios processed:
```
python stashStudioMatchScrape.py --all --limit 10
```

Preview changes without applying them (dry run):
```
python stashStudioMatchScrape.py --all --dry-run
```

### As a Stash plugin

Once installed as a plugin, you can use it in several ways:

1. **From the Studio Page**: 
   - Navigate to any studio in Stash
   - Click on the "..." menu
   - Select "Studio Match Scrape" from the plugins menu
   - The plugin will attempt to match and update that specific studio

2. **Batch Processing via Tasks**:
   - Go to Settings > Tasks
   - Find "Match All Studios" in the list
   - Click "Run" to process all studios in your database
   - Alternatively, use "Match All Studios (Dry Run)" to preview changes without applying them

3. **Automatic Processing (Optional)**:
   - The plugin can automatically run whenever a studio is updated
   - This feature can be enabled or disabled in the plugin settings
   - Go to Settings > Plugins > Studio Match Scrape
   - Toggle the "Enable Automatic Updates" setting

## Plugin Settings

The plugin has the following configurable settings:

- **Enable Automatic Updates**: When enabled, the plugin will automatically run whenever a studio is created or updated. This helps keep your studios in sync with external databases without manual intervention.
- **Dry Run Mode**: When enabled, the plugin will show what changes would be made without actually making them. This is useful for previewing the effects of the plugin before committing changes.

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

## Getting API Keys

### Stash API Key
1. Go to Settings > Security > API Keys in your Stash instance
2. Create a new API key with appropriate permissions

### ThePornDB API Key
1. Register at [ThePornDB](https://theporndb.net/)
2. Request an API key from your account page

### StashDB API Key
1. Register at [StashDB](https://stashdb.org/)
2. Request an API key from your account page

## How It Works

The script works by:
1. Retrieving all studios from your Stash database
2. For each studio, searching for exact name matches on ThePornDB and StashDB
3. When a match is found, retrieving detailed information about the studio
4. Updating your local studio with the new information, including:
   - Setting the correct parent studio (creating it if necessary)
   - Adding StashDB and ThePornDB IDs
   - Updating the studio URL and image

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

## Troubleshooting

- **API Key Issues**: Ensure your API keys are correctly entered in the config.py file
- **Connection Problems**: Verify your Stash server address and port in the configuration
- **Log Files**: Check the `studio_match_progress.log` file for detailed error messages
- **Permission Issues**: Make sure the script has permission to write to the log file
- **Plugin Not Appearing**: Verify that the plugin directory structure is correct and that the .yml file is properly formatted
- **Python Path Issues**: If using the plugin in Stash, make sure Python is in your system PATH

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT License](LICENSE) 