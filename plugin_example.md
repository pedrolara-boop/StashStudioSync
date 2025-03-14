# StashStudioMetadataMatcher Plugin Example

This document provides examples of how to use the StashStudioMetadataMatcher plugin with Stash.

## Plugin Directory Structure

When installed as a plugin, your directory structure should look like this:

```
~/.stash/plugins/StashStudioMetadataMatcher/
├── config.py                      # Your configuration file with API keys
├── config_template.py             # Template configuration file
├── LICENSE                        # License file
├── plugin_example.md              # This example file
├── README.md                      # Main documentation
├── requirements.txt               # Python dependencies
├── stashStudioMetadataMatcher.py  # Main script
└── stashStudioMetadataMatcher.yml # Plugin configuration file
```

## Plugin Configuration

The plugin is configured through the `stashStudioMetadataMatcher.yml` file, which defines:

1. **Tasks** - Operations that can be run from the Stash Tasks page
2. **Settings** - User-configurable options for the plugin

## Step-by-Step Installation Guide

### 1. Download the Plugin

First, you need to download the plugin to your Stash plugins directory:

```bash
# Navigate to your Stash plugins directory
cd ~/.stash/plugins

# Clone the repository
git clone https://github.com/yourusername/StashStudioMetadataMatcher.git

# Enter the plugin directory
cd StashStudioMetadataMatcher
```

### 2. Set Up Configuration

The plugin requires API keys to function properly:

```bash
# Create your configuration file from the template
cp config_template.py config.py

# Edit the configuration file with your favorite text editor
nano config.py  # or use vim, emacs, or any text editor
```

Edit the `config.py` file to include your API keys:

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

### 3. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 4. Activate the Plugin

Restart Stash or reload plugins from the Settings page:

1. Go to Settings > Plugins
2. Click "Reload Plugins"
3. Verify that "StashStudioMetadataMatcher" appears in the list

## Example: Running as a Task

The plugin provides several tasks to update studios in your database:

### Match All Studios

To run the "Match All Studios" task:

1. Go to Settings > Tasks
2. Find "Match All Studios" in the list
3. Click "Run"

This will process all studios in your database and update them with information from ThePornDB and StashDB.

### Match All Studios (Dry Run)

To preview changes without applying them:

1. Go to Settings > Tasks
2. Find "Match All Studios (Dry Run)" in the list
3. Click "Run"

This will show what changes would be made without actually making them.

### Force Update All Studios

To update all studios, even if they already have all information:

1. Go to Settings > Tasks
2. Find "Force Update All Studios" in the list
3. Click "Run"

This is useful for refreshing metadata or applying changes from updated external databases.

## Example: Running from Studio Page

You can also run the plugin directly from a studio's page:

1. Navigate to any studio in Stash
2. Click on the "..." menu in the top-right corner
3. Look for "StashStudioMetadataMatcher" in the plugins menu
4. Click it to run the plugin on that specific studio

## Debugging

If you encounter issues with the plugin, check the following:

1. The log file at `studio_metadata_matcher.log` in the plugin directory
2. The Stash logs (Settings > Logs)
3. Make sure Python is installed and in your system PATH
4. Verify that all required Python dependencies are installed

### Common Issues and Solutions

#### Plugin Not Appearing in Stash

If the plugin doesn't appear in Stash:

1. Check that the directory structure is correct
2. Verify that the YAML file is properly formatted
3. Restart Stash completely
4. Check Stash logs for any error messages

#### API Key Issues

If the plugin runs but doesn't update any studios:

1. Verify that your API keys are correctly entered in `config.py`
2. Check that you have valid and active API keys for ThePornDB and StashDB
3. Ensure your Stash API key has the necessary permissions

#### Python Issues

If you encounter Python-related errors:

1. Verify that Python 3.6 or higher is installed
2. Make sure Python is in your system PATH
3. Check that all dependencies are installed with `pip install -r requirements.txt`
4. Try running the script directly from the command line to see any error messages

## Advanced: Custom Configuration

You can customize the plugin's behavior by editing the `config.py` file. This allows you to:

1. Change the Stash server address and port
2. Update your API keys
3. Modify the log file location

Remember to restart Stash or reload plugins after making changes to the configuration.

## Best Practices

For the best results with this plugin:

1. **Run Regularly**: Schedule regular runs to keep your studios updated
2. **Use Dry Run First**: Always use dry run mode first to preview changes
3. **Check Logs**: Review the log file to see what changes were made
4. **Manual Verification**: Manually verify studios that couldn't be automatically matched
5. **Keep API Keys Updated**: Ensure your API keys are valid and up-to-date 