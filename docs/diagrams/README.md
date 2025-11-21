# D2 Architecture Diagrams

This directory contains D2 source files for the Ionosense HPC architecture documentation.

**Last Updated:** 2025-01-20 (v0.9.4+ executor-based architecture, D2 migration)

## Diagram Organization

Diagrams are organized by prefix to indicate their scope:

- **`cpp_*`** - C++ implementation details (classes, components, memory, sequences)
- **`py_*`** - Python layer and workflows (packages, analysis, experimental workflows)
- **`sys_*`** - System-level overviews (platform architecture, integrations)

## Available Diagrams

### C++ Architecture (`cpp_*`)

| File | Layout | Type | Description |
|------|--------|------|-------------|
| `cpp_class_hierarchy.d2` | dagre | Class | Complete C++ class hierarchy with executor pattern, BatchExecutor, StreamingExecutor, ring buffers, CUDA resources, and exception handling |
| `cpp_components_pipeline.d2` | dagre | Component | High-level component relationships showing dual executor architecture and data flow |
| `cpp_sequence_execution.d2` | elk | Sequence | Combined execution flows for BatchExecutor and StreamingExecutor pipelines |
| `cpp_memory_layout.d2` | dagre | Memory | Memory layouts and data flow patterns for both BatchExecutor and StreamingExecutor |

### Python Layer (`py_*`)

| File | Layout | Type | Description |
|------|--------|------|-------------|
| `py_package_architecture.d2` | dagre | Package | Python package structure with executor bindings, benchmarks, config, utils, and GPU clock management |
| `py_analysis_workflow.d2` | dagre | Component | Experiment and analysis architecture with Streamlit (PRIMARY) and Quarto (FUTURE) reporting layers |
| `py_workflow_sequence.d2` | elk | Sequence | Complete experimental workflow including ionoc, iprof, Streamlit dashboard, and GPU clock locking |

### System Overview (`sys_*`)

| File | Layout | Type | Description |
|------|--------|------|-------------|
| `sys_architecture_overview.d2` | elk | Overview | Platform overview with CLI tools (ionoc, iprof, iono dashboard), Streamlit, and system integrations |

**Total:** 8 technical diagrams covering C++, Python, and system architecture

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

**Examples:** `cpp_class_hierarchy.d2`, `cpp_components_pipeline.d2`, `py_package_architecture.d2`

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

**Examples:** `cpp_sequence_execution.d2`, `sys_architecture_overview.d2`, `py_workflow_sequence.d2`

## Rendering Diagrams

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

### Generate SVG Files

Each D2 file specifies its recommended layout engine in the header comment.

**Single diagram:**
```bash
# Using dagre (for hierarchical layouts)
d2 --layout dagre docs/diagrams/src/cpp_class_hierarchy.d2 docs/diagrams/generated/cpp_class_hierarchy.svg

# Using elk (for complex graphs)
d2 --layout elk docs/diagrams/src/sys_architecture_overview.d2 docs/diagrams/generated/sys_architecture_overview.svg
```

**All diagrams (PowerShell script - recommended):**
```powershell
# Create a rendering script (docs/diagrams/render_all.ps1)
$diagrams = @{
    "cpp_class_hierarchy.d2" = "elk"
    "cpp_components_pipeline.d2" = "dagre"
    "cpp_sequence_execution.d2" = "elk"
    "cpp_memory_layout.d2" = "elk"
    "py_package_architecture.d2" = "dagre"
    "py_analysis_workflow.d2" = "dagre"
    "py_workflow_sequence.d2" = "elk"
    "sys_architecture_overview.d2" = "elk"
}

foreach ($diagram in $diagrams.GetEnumerator()) {
    $src = "docs/diagrams/src/$($diagram.Key)"
    $out = "docs/diagrams/generated/$($diagram.Key.Replace('.d2', '.svg'))"
    Write-Host "Rendering $($diagram.Key) with $($diagram.Value)..."
    d2 --layout $diagram.Value $src $out
}
```

**All diagrams (Bash script):**
```bash
# Create a rendering script (docs/diagrams/render_all.sh)
#!/bin/bash

declare -A diagrams=(
    ["cpp_class_hierarchy.d2"]="elk"
    ["cpp_components_pipeline.d2"]="dagre"
    ["cpp_sequence_execution.d2"]="elk"
    ["cpp_memory_layout.d2"]="elk"
    ["py_package_architecture.d2"]="dagre"
    ["py_analysis_workflow.d2"]="dagre"
    ["py_workflow_sequence.d2"]="elk"
    ["sys_architecture_overview.d2"]="elk"
)

for diagram in "${!diagrams[@]}"; do
    layout="${diagrams[$diagram]}"
    src="docs/diagrams/src/$diagram"
    out="docs/diagrams/generated/${diagram%.d2}.svg"
    echo "Rendering $diagram with $layout..."
    d2 --layout "$layout" "$src" "$out"
done
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
