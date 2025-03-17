# Stash StudioSync Plugin

A Stash plugin that completes missing studio information by matching and syncing with ThePornDB, StashDB, and other Stash-box endpoints. Update a single studio using the UI button or batch match your entire collection.

## Features

- 🔄 **Multi-Endpoint Sync**: Works with ThePornDB, StashDB, and other Stash-box endpoints
- 👨‍👦 **Parent Studio Handling**: Automatically creates and links parent studios
- 🖼️ **Image Updates**: Automatically adds missing logos images for studios
- 🔍 **Intelligent Matching**: Fuzzy name matching for better results
- 🎯 **Flexible Updates**: Both batch processing and single studio updates

## Installation

1. Clone the repository and copy the plugin to your Stash plugins directory:
   ```bash
   # First clone the repository
   git clone https://github.com/pedrolara-boop/boop-stash.git
   
   # Copy the StudioSync plugin folder to your Stash plugins directory
   cp -r boop-stash/plugins/StudioSync ~/.stash/plugins/
   ```

2. Install the Python requirements:
   ```bash
   pip install -r requirements.txt
   ```

3. Reload plugins in Stash (Settings > Plugins > Reload plugins)

## Usage

### Single Studio Update
![Match Button](button.png)
- Use the "Match Metadata" button on any studio page
- Updates just that studio with latest information

### Batch Updates
![Plugin Tasks](screenshot.png)

Available in Settings > Tasks:
1. **Match Studios**: Update all studios missing information
2. **Match Studios (Dry Run)**: Preview changes without applying them
3. **Force Update Studios**: Update all studios with latest data
4. **Force Update Studios (Dry Run)**: Preview all potential updates

## Requirements

- Python 3.6 or higher
- Python packages: requests, thefuzz, stashapi

## Support

- [Report Issues](https://github.com/pedrolara-boop/boop-stash/issues)
- [GitHub Repository](https://github.com/pedrolara-boop/boop-stash)

## License

MIT License - See LICENSE file for details 
