# StashStudioMetadataMatcher Script

The standalone script version with additional features for advanced users who need more control over the matching process.

## Key Differences from Plugin

- 🎯 **Individual Studio Processing**: Match studios by ID or name
- ⚙️ **More Configuration Options**: Fine-tune the matching process
- 🔢 **Batch Control**: Limit the number of studios processed
- 📊 **Lower Default Threshold**: 85% for fuzzy matching (vs 95% in plugin)
- 🛠️ **Command Line Interface**: Full control via CLI arguments

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/pedrolara-boop/StashStudioMetadataMatcher.git
   cd StashStudioMetadataMatcher
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Choose one of these methods:

### Method 1: Configuration File (Recommended)
1. Create from template:
   ```bash
   cp config_template.py config.py
   ```

2. Edit `config.py`:
   ```python
   config = {
       'scheme': 'http',
       'host': 'localhost',
       'port': 9999,
       'api_key': '',            # Your Stash API key
       'tpdb_api_key': '',       # Your ThePornDB API key
       'stashdb_api_key': '',    # Your StashDB API key
       'log_file': 'studio_metadata_matcher.log',
       'fuzzy_threshold': 85,    # Default threshold for script
       'use_fuzzy_matching': True,
   }
   ```

### Method 2: Environment Variables
```bash
export STASH_SCHEME=http
export STASH_HOST=localhost
export STASH_PORT=9999
export STASH_API_KEY=your_stash_key
export TPDB_API_KEY=your_tpdb_key
export STASHDB_API_KEY=your_stashdb_key
```

## Basic Usage

### Process All Studios
```bash
python stashStudioMetadataMatcher.py --all
```

### Process Single Studio
By ID:
```bash
python stashStudioMetadataMatcher.py --id 123
```

By Name:
```bash
python stashStudioMetadataMatcher.py --name "Studio Name"
```

### Preview Changes
```bash
python stashStudioMetadataMatcher.py --all --dry-run
```

### Force Update
```bash
python stashStudioMetadataMatcher.py --all --force
```

## Advanced Usage

### Batch Processing
Process 50 studios at a time:
```bash
python stashStudioMetadataMatcher.py --all --limit 50
```

### Fuzzy Matching Control
Adjust threshold:
```bash
python stashStudioMetadataMatcher.py --all --fuzzy-threshold 80
```

Disable fuzzy matching:
```bash
python stashStudioMetadataMatcher.py --all --no-fuzzy
```

### Debug Mode
```bash
python stashStudioMetadataMatcher.py --all --debug
```

## Command Line Reference

| Argument | Description | Default | Example |
|----------|-------------|---------|---------|
| `--all` | Process all studios | - | `--all` |
| `--id ID` | Process by ID | - | `--id 123` |
| `--name NAME` | Process by name | - | `--name "Studio"` |
| `--limit N` | Limit batch size | None | `--limit 50` |
| `--dry-run` | Preview only | False | `--dry-run` |
| `--force` | Update all | False | `--force` |
| `--fuzzy-threshold N` | Match threshold | 85 | `--fuzzy-threshold 90` |
| `--no-fuzzy` | Disable fuzzy | False | `--no-fuzzy` |
| `--debug` | Debug logging | False | `--debug` |
| `--host` | Stash host | config | `--host localhost` |
| `--port` | Stash port | config | `--port 9999` |
| `--scheme` | HTTP scheme | config | `--scheme https` |

## Best Practices

### Initial Setup
1. Start with a dry run:
   ```bash
   python stashStudioMetadataMatcher.py --all --dry-run
   ```

2. Process a small batch:
   ```bash
   python stashStudioMetadataMatcher.py --all --limit 10
   ```
3. Review logs before proceeding

### Troubleshooting

#### Common Issues

1. **Connection Errors**
   - Check Stash is running
   - Verify host/port settings
   - Ensure API keys are valid

2. **No Matches Found**
   - Lower fuzzy threshold
   - Check studio names
   - Enable debug logging


#### Logs
Check `studio_metadata_matcher.log` for:
- Match attempts
- Update details
- Error messages
- Performance data

## Examples

### Basic Workflow
```bash
# 1. Preview changes
python stashStudioMetadataMatcher.py --all --dry-run

# 2. Process in batches
python stashStudioMetadataMatcher.py --all --limit 50

# 3. Force update specific studio
python stashStudioMetadataMatcher.py --name "Problem Studio" --force

# 4. Regular maintenance
python stashStudioMetadataMatcher.py --all
```

### Advanced Usage
```bash
# Process with custom settings
python stashStudioMetadataMatcher.py --all \
    --fuzzy-threshold 80 \
    --limit 100 \
    --debug

# Force update with strict matching
python stashStudioMetadataMatcher.py --all \
    --force \
    --no-fuzzy
``` 