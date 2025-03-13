# Studio Match Scrape Plugin Example

This document provides examples of how to use the Studio Match Scrape plugin with Stash.

## Plugin Directory Structure

When installed as a plugin, your directory structure should look like this:

```
~/.stash/plugins/stashStudioMatchScrape/
├── config.py                  # Your configuration file with API keys
├── config_template.py         # Template configuration file
├── LICENSE                    # License file
├── plugin_example.md          # This example file
├── README.md                  # Main documentation
├── requirements.txt           # Python dependencies
├── stashStudioMatchScrape.py  # Main script
└── stashStudioMatchScrape.yml # Plugin configuration file
```

## Plugin Configuration

The plugin is configured through the `stashStudioMatchScrape.yml` file, which defines:

1. **Tasks** - Operations that can be run from the Stash Tasks page
2. **Hooks** - Operations that run automatically when certain events occur
3. **Settings** - User-configurable options for the plugin

## Plugin Settings

The plugin has the following settings that can be configured from the Stash UI:

- **Enable Automatic Updates** - When enabled, the plugin will automatically run whenever a studio is created or updated. This helps keep your studios in sync with external databases without manual intervention.

To access these settings:
1. Go to Settings > Plugins
2. Find "Studio Match Scrape" in the list
3. Click on the settings icon (gear)
4. Toggle the "Enable Automatic Updates" setting as desired
5. Click "Save"

## Example: Running as a Task

The plugin provides a task to update all studios in your database:

To run the "Match All Studios" task:

1. Go to Settings > Tasks
2. Find "Match All Studios" in the list
3. Click "Run"

## Example: Using the Hook

The plugin can automatically run when a studio is updated. This happens in the background and requires no user intervention.

When you:
1. Create a new studio
2. Edit an existing studio
3. Save changes to a studio

The plugin will automatically try to match the studio with ThePornDB and StashDB and update its metadata, but only if the "Enable Automatic Updates" setting is turned on.

## Example: Running from Studio Page

You can also run the plugin directly from a studio's page:

1. Navigate to any studio in Stash
2. Click on the "..." menu in the top-right corner
3. Look for "Studio Match Scrape" in the plugins menu
4. Click it to run the plugin on that specific studio

## Debugging

If you encounter issues with the plugin, check the following:

1. The log file at `studio_match_progress.log` in the plugin directory
2. The Stash logs (Settings > Logs)
3. Make sure Python is installed and in your system PATH
4. Verify that all required Python dependencies are installed
5. Check if the "Enable Automatic Updates" setting is configured as expected

## Advanced: Custom Configuration

You can customize the plugin's behavior by editing the `config.py` file. This allows you to:

1. Change the Stash server address and port
2. Update your API keys
3. Modify the log file location

Remember to restart Stash or reload plugins after making changes to the configuration. 