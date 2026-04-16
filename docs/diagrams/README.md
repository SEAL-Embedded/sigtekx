# D2 Architecture Diagrams

This directory contains D2 source files for the SigTekX architecture documentation.

**Last Updated:** 2025-01-20 (v0.9.4+ executor-based architecture, D2 migration)

## Quick Access

| Section | Description |
|---------|-------------|
| **[CLI Usage](#quick-start-cli---recommended)** | Generate diagrams with `sigx diagrams` - smart regeneration, format options, batch processing |
| **[Available Diagrams](#available-diagrams)** | 10 technical diagrams: C++ architecture (6), Python layer (3), System overview (1) |
| **[Direct D2 Commands](#direct-d2-commands)** | Manual single-diagram generation for development and advanced control |
| **[Layout Engines](#layout-engines)** | dagre (hierarchical) vs elk (complex graphs) - when to use each |
| **[Output Formats](#output-formats)** | SVG (default), PNG, PDF support |
| **[VS Code Integration](#vs-code-integration)** | Live preview extension for editing D2 files |
| **[Maintenance](#maintenance)** | How to update diagrams and keep documentation in sync |
| **[Resources](#resources)** | Official D2 documentation, playground, examples |

---

## Diagram Organization

Diagrams use a numbered naming scheme for logical ordering:

- **`01-09`** - Numbered diagrams following the architecture progression (system → Python → C++)
- **`cpp_class_hierarchy.d2`** - Reference diagram (not numbered for easy reference)

## Available Diagrams

### System Overview

| File | Layout | Type | Description |
|------|--------|------|-------------|
| `01_system_overview.d2` | elk | Overview | Compact project overview for portfolio display — signal flow, engine, workflow, applications |
| `01b_system_overview_full.d2` | elk | Overview | Comprehensive system architecture — executors, pipeline stages, CUDA resources, research workflow, dev tools |

### Python Layer

| File | Layout | Type | Description |
|------|--------|------|-------------|
| `02_py_structure.d2` | dagre | Package | Python package structure with executor bindings, benchmarks, config, utils, and GPU clock management |
| `04_py_analysis.d2` | dagre | Component | Experiment and analysis architecture with Streamlit (PRIMARY) and Quarto (FUTURE) reporting layers |
| `05_workflow_full.d2` | elk | Sequence | Complete experimental workflow including sigxc, sxp, Streamlit dashboard, and GPU clock locking |

### C++ Architecture

| File | Layout | Type | Description |
|------|--------|------|-------------|
| `03_cpp_components.d2` | dagre | Component | High-level component relationships showing dual executor architecture and data flow |
| `06_cpp_seq_batch.d2` | elk | Sequence | BatchExecutor execution flow (high-throughput, 86.79 µs) |
| `07_cpp_seq_stream.d2` | elk | Sequence | StreamingExecutor execution flow (low-latency streaming, 122.25 µs) |
| `08_cpp_mem_batch.d2` | elk | Memory | BatchExecutor memory layout (164 KB, direct pipeline) |
| `09_cpp_mem_stream.d2` | elk | Memory | StreamingExecutor memory layout (295 KB, ring buffer architecture) |
| `cpp_class_hierarchy.d2` | elk | Class | Complete C++ class hierarchy with executor pattern, BatchExecutor, StreamingExecutor, ring buffers, CUDA resources, and exception handling |

**Total:** 10 technical diagrams covering system architecture, Python layer, and C++ implementation

## Layout Engines

D2 supports multiple layout engines with different strengths. This project uses two:

### dagre (Hierarchical Layouts)

**Use for:**
- Class hierarchies and inheritance
- Component relationships
- Memory layouts
- Package structures
- Simple workflows

**Characteristics:**
- Fast and predictable
- Clean hierarchical organization
- Top-to-bottom or left-to-right flow
- Best for tree-like structures

**Examples:** `02_py_structure.d2`, `03_cpp_components.d2`, `04_py_analysis.d2`

### elk (Complex Graph Layouts)

**Use for:**
- Sequence diagrams with many actors
- Complex workflows with crossing edges
- System overviews with multiple subsystems
- Diagrams with many interconnections

**Characteristics:**
- More sophisticated layout algorithm
- Better handling of edge crossings
- Slower than dagre but produces cleaner complex graphs
- Best for intricate relationships

**Examples:** `01_system_overview.d2`, `05_workflow_full.d2`, `06_cpp_seq_batch.d2`, `07_cpp_seq_stream.d2`, `08_cpp_mem_batch.d2`, `09_cpp_mem_stream.d2`, `cpp_class_hierarchy.d2`

## Rendering Diagrams

### Quick Start (CLI - Recommended)

The easiest way to generate diagrams is using the `sigx diagrams` command, which handles layout engine selection automatically:

```bash
# Generate all diagrams (smart regeneration - only if source changed)
sigx diagrams

# Force regenerate all diagrams (ignore timestamps)
sigx diagrams --force

# Generate by category
sigx diagrams cpp        # C++ diagrams only
sigx diagrams py         # Python diagrams only
sigx diagrams sys        # System diagrams only

# Generate specific diagram
sigx diagrams cpp_class_hierarchy
sigx diagrams 02_py_structure
sigx diagrams 04_py_analysis

# Change output format (default: svg)
sigx diagrams --format png       # All as PNG
sigx diagrams cpp --format pdf   # C++ diagrams as PDF
sigx diagrams 01_system_overview --format pdf

# Shortcut (same as 'sigx diagrams')
idiag cpp --format png
```

**Features:**
- **Smart regeneration**: Automatically skips up-to-date diagrams (checks file timestamps)
- **Layout engine selection**: Uses the correct layout engine for each diagram (no need to remember)
- **Format support**: SVG (default), PNG, or PDF output
- **Batch processing**: Generate multiple diagrams at once
- **Verbose mode**: Add `--verbose` to see detailed d2 output

**Note:** The CLI is integrated with the dev environment (see `scripts/init_pwsh.ps1`). Tab completion is available for all commands, targets, and flags.

### Install D2

**Windows (Scoop):**
```powershell
scoop install d2
```

**macOS (Homebrew):**
```bash
brew install d2
```

**Linux:**
```bash
curl -fsSL https://d2lang.com/install.sh | sh
```

### Direct D2 Commands

For single diagram generation or when you need full control over d2 options, use direct d2 commands. Each D2 file specifies its recommended layout engine in the header comment.

**Single diagram (most robust for development):**
```bash
# Using dagre (for hierarchical layouts)
d2 --layout dagre docs/diagrams/src/cpp_class_hierarchy.d2 docs/diagrams/generated/cpp_class_hierarchy.svg

# Using elk (for complex graphs)
d2 --layout elk docs/diagrams/src/01_system_overview.d2 docs/diagrams/generated/01_system_overview.svg
```

### Output Formats

D2 supports multiple output formats:

```bash
# SVG (recommended, scalable)
d2 --layout dagre input.d2 output.svg

# PNG (raster, specify resolution)
d2 --layout dagre input.d2 output.png

# PDF (publication quality)
d2 --layout dagre input.d2 output.pdf
```

### VS Code Integration

For live preview while editing:
1. Install the "D2" extension by Terrastruct
2. Open any `.d2` file
3. Press `Ctrl+Shift+P` and run "D2: Preview"
4. The preview updates automatically as you edit

## Diagram Standards

All diagrams follow professional documentation standards:

- **Consistent Styling**: Color schemes, shapes, and typography match across diagrams
- **Clear Notation**: Relationships and data flow are explicitly labeled
- **Documentation**: Inline comments explain complex sections
- **Maintainability**: Code is organized with logical sections and grouping
- **Header Template**: Each file includes layout engine choice and brief description

### File Header Template

```d2
# [Diagram Name]
# Layout: [dagre|elk] - [brief reason]
# Render: See docs/diagrams/README.md for rendering instructions
#
# [Brief description of diagram purpose]
```

## Integration with Documentation

These diagrams are referenced in:
- `docs/ARCHITECTURE.md` - Main architecture documentation
- `README.md` - Project overview
- API documentation - Implementation details
- Research papers and presentations

## Maintenance

When updating the architecture:
1. **Edit the `.d2` source file** in `docs/diagrams/src/`
2. **Regenerate SVG** using the appropriate layout engine (see file header)
3. **Commit source file** to version control
4. **Optionally commit generated SVG** for documentation embedding
5. **Update references** in documentation if diagram scope changes

**Important:** The `.d2` source files are the authoritative version - always edit the source files rather than manually creating diagrams.

## Legacy PlantUML Diagrams

Previous PlantUML diagrams have been migrated to D2 and are archived in `docs/diagrams/src/puml legacy/` for reference. All future updates should be made to D2 files only.

## Resources

- [D2 Documentation](https://d2lang.com/)
- [D2 Playground](https://play.d2lang.com/) - Test diagrams online
- [Layout Engine Comparison](https://d2lang.com/tour/layouts/) - Visual guide to dagre vs elk
- [D2 Examples](https://github.com/terrastruct/d2/tree/master/docs/examples) - Gallery of diagram types
