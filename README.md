# StudioSync Plugin

A Stash plugin for automatically matching and updating studios with metadata from all configured Stash-box endpoints.

## Features

- 🔄 **Multi-Endpoint Support**: Works with all your configured Stash-box endpoints (ThePornDB, StashDB, and any additional Stash-box endpoints)
- 👨‍👦 **Parent Studio Management**: Automatically creates and links parent studios
- 🔗 **URL Updates**: Retrieves and updates studio URLs, prioritizing official/home URLs
- 🖼️ **Image Updates**: Fetches and updates studio images
- 🧠 **Intelligent Data Merging**: Combines data from multiple sources intelligently
- 🔍 **Fuzzy Matching**: Smart name matching with configurable threshold (default: 95)
- 📝 **Detailed Logging**: Rotating logs with progress tracking and detailed updates
- 🔒 **No Configuration Needed**: Uses your existing Stash API keys and endpoint settings
- 🎯 **One-Click Updates**: Adds a "Match Metadata" button to studio pages for instant matching

## Installation

1. Clone the repository to your Stash plugins directory:
   ```bash
   cd ~/.stash/plugins  # Adjust path according to your Stash installation
   git clone https://github.com/pedrolara-boop/StudioSync.git
   cd StudioSync
   ```

2. Install the Python requirements:
   ```bash
   pip install -r requirements.txt
   ```
   
   Required packages:
   - requests
   - thefuzz
   - stashapi
   - python-Levenshtein (optional but improves fuzzy matching performance)

3. Reload plugins in Stash:
   - Go to Settings
   - Click on "Plugins" in the left sidebar
   - Click the "Reload" button

4. Verify installation:
   - Go to Settings > Tasks
   - You should see "StudioSync" in the tasks list
   - Available tasks should look like this:
     ![Plugin Tasks Screenshot](screenshot.png)

> **Note**: Make sure Python 3.6 or higher is installed on your system. For Docker installations, you may need to install Python and the requirements inside your container.

## Requirements

- Python 3.6 or higher
- Required Python packages:
  - requests
  - thefuzz
  - stashapi
  - python-Levenshtein # Optional but improves thefuzz performance

## Usage

### Studio Button

The plugin adds a "Match Metadata" button to each studio page:
- Located in the studio edit toolbar
- One-click matching with all configured endpoints
- Automatically creates and links parent studios
- Shows real-time status (matching, success, error)
- Reloads the page after successful updates
- Forces update to get latest metadata

### Plugin Tasks

Access the plugin tasks in Stash under Settings > Plugin Tasks:

1. **Match Studios**
   - Updates studios with metadata from all configured endpoints
   - Creates/links parent studios automatically
   - Updates URLs and images
   - Uses fuzzy matching with 95% threshold

2. **Match Studios (Dry Run)**
   - Preview changes without applying them
   - Shows potential matches from all endpoints
   - Great for checking what would be updated

3. **Force Update Studios**
   - Updates all studios, even those with existing data
   - Gets latest metadata from all endpoints
   - Useful for complete refresh

4. **Force Update Studios (Dry Run)**
   - Preview all potential updates
   - Shows what would change in force mode
   - No changes are made

### Configuration

No separate configuration file needed! The plugin uses:
- Your configured Stash-box endpoints and API keys
- Default fuzzy matching threshold of 95%
- Automatic log rotation (10MB per file, 5 backup files)

### Logs

Logs are stored in the plugin directory:
- `studiosync.log` (current log)
- Rotated logs: `.log.1` through `.log.5`
- Maximum 50MB total log storage

## Looking for Script Version?

If you need the standalone script version with additional features like matching by ID or name, check [SCRIPT.md](SCRIPT.md).

## Support

- [Report Issues](https://github.com/pedrolara-boop/StudioSync/issues)
- [GitHub Repository](https://github.com/pedrolara-boop/StudioSync)

## License

MIT License - See LICENSE file for details 