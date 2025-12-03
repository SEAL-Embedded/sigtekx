# Ionosense HPC D2 Diagram Color Scheme

**Version**: 1.0
**Last Updated**: 2025-01-20

This document defines the visual language used across all Ionosense HPC architecture diagrams. All diagrams import shared styles from `docs/diagrams/src/common/styles.d2`.

## Purpose

Consistent color coding helps readers quickly understand:
- **Component types** (platform, execution, analysis, etc.)
- **Memory spaces** (GPU, host, transfers)
- **Relationships** (dependency, ownership, data flow)
- **Architectural layers** and their interactions

## Container Colors (Primary Groupings)

| Style Class | Fill Color | Stroke | Use Case |
|-------------|------------|--------|----------|
| `core-blue` | #E6F3FF | #4169E1 | Core platform, executors, C++ architecture |
| `core-blue-emphasis` | #E6F3FF | #4169E1 (thick) | Emphasized core components |
| `execution-red` | #FFE6E6 | #C00000 | Execution layer, workflow phases |
| `streaming-green` | #E6FFE6 | #228B22 | Streaming components, analysis |
| `benchmark-orange` | #FFF5E6 | #FF8C00 | Benchmarks, artifacts, results |
| `config-blue` | #F0F8FF | #4169E1 | Configuration, orchestration |
| `note-gold` | #FFFACD | #FFD700 | Notes, capabilities, highlights |
| `research-green` | #E8F5E9 | #4CAF50 | Research applications, impact |
| `batch-blue` | #F0F8FF | #4169E1 | Batch mode operations |
| `loop-container` | #F0FFF0 | #228B22 (dashed) | Loop/iteration containers |
| `optional-orange` | #FFF5E6 | #FF8C00 (dashed) | Future/optional features |

## Functional Component Colors

| Style Class | Fill Color | Stroke | Use Case |
|-------------|------------|--------|----------|
| `config-schema` | #B3D9FF | #4169E1 | Configuration & schema classes |
| `builder-pattern` | #B8D8F5 | #4169E1 | Builder/factory pattern classes |
| `utility-module` | #CCE5FF | #5B9BD5 | Utility function modules |
| `profiling-tool` | #FFD699 | #FF8C00 | Profiling & performance tools |
| `base-class` | #E6D7B8 | #B8860B | Abstract base classes |
| `future-feature` | #FFE680 | #DAA520 (dashed) | Experimental features |

## Memory Space Colors

| Style Class | Fill Color | Stroke | Use Case |
|-------------|------------|--------|----------|
| `gpu-memory` | #FFD700 | #B8860B | GPU device memory |
| `host-memory` | #90EE90 | #228B22 | Pinned host memory |
| `ring-buffer` | #C4E6C4 | #228B22 | Per-channel ring buffers |
| `pcie-transfer` | #FFE4E4 | #C00000 | Host ↔ Device transfers |
| `host-memory-streaming` | #E6FFE6 | #228B22 | Streaming host memory |

## CUDA / Kernel Colors

| Style Class | Fill Color | Stroke | Use Case |
|-------------|------------|--------|----------|
| `kernel-orange` | #FFE4B5 | #FF8C00 | CUDA kernels, GPU code |
| `cuda-resource` | #D4E6FF | #4169E1 | CUDA resource management |

## Exception / Error Colors

| Style Class | Fill Color | Stroke | Use Case |
|-------------|------------|--------|----------|
| `exception-light` | #FFE6E6 | #FF6B6B | Exception handling |
| `exception-pink` | #FFB6C1 | #FF6B6B | Base exception classes |

## Relationship Styles

| Style Class | Appearance | Use Case |
|-------------|------------|----------|
| `dependency` | Dashed line (stroke-dash: 3) | Loose coupling, optional dependencies |
| `ownership` | Diamond arrowhead | Composition/ownership relationships |
| `implementation` | Dashed + triangle arrowhead | Interface implementation |
| `data-flow` | Solid line, stroke-width: 2 | Data movement between components |
| `connection-emphasis` | Solid line, stroke-width: 3 | Critical/emphasized connections |

## Text Styles

| Style Class | Appearance | Use Case |
|-------------|------------|----------|
| `text-note` | Italic, font-size: 12, no border | Metadata, annotations |
| `section-header` | Bold, font-size: 14, no border | Section titles |
| `text-label` | Standard text, no border | Inline labels |

## Shape Classes

| Style Class | D2 Shape | Use Case |
|-------------|----------|----------|
| `storage-cylinder` | `cylinder` | Databases, storage systems |
| `actor-person` | `person` | Human actors, users |
| `class-shape` | `class` | UML class diagrams |
| `box-rectangle` | `rectangle` | Default component shape |
| `text-shape` | `text` | Pure text elements |

## Usage Guidelines

### Container Colors
- Use **core-blue** for primary architectural components (executors, stages, core platform)
- Use **execution-red** for workflow phases and execution orchestration
- Use **streaming-green** for continuous data flows and real-time analysis
- Use **benchmark-orange** for performance measurement and profiling
- Use **note-gold** for informational callouts and capability highlights
- Use **research-green** for research applications and scientific impact

### Memory Space Colors
- Use **gpu-memory** for all device memory allocations (show as cylinders)
- Use **host-memory** for page-locked host buffers (show as cylinders)
- Use **pcie-transfer** for explicit H2D/D2H transfer operations
- Use **ring-buffer** for StreamingExecutor per-channel buffers

### Relationship Guidelines
- Use **dependency** (dashed) for optional or configuration-driven relationships
- Use **ownership** (diamond) when one component owns/manages another
- Use **implementation** (dashed + triangle) for interface implementations
- Use **data-flow** (thick solid) for primary data movement paths
- Avoid excessive arrow styling - let content speak for itself

### Diagram-Specific Legends

Each diagram includes a **simplified legend** showing only colors used in that diagram:
- **01_system_overview.d2**: Full legend (reference for all diagrams)
- **02_py_structure.d2**: Python package colors (config, utility, profiling)
- **03_cpp_components.d2**: Core platform colors (blue, red, green, orange)
- **08_cpp_mem_batch.d2**: Memory space colors (GPU, host, PCIe)
- **09_cpp_mem_stream.d2**: Memory space + ring buffer colors

## Example Usage

```d2
# Import shared styles
...@common/styles

# Apply container color
my_container: My Container {
  class: core-blue
}

# Apply functional color
config_class: ConfigClass {
  class: config-schema
}

# Apply relationship style
a -> b: depends on {
  class: dependency
}

# Apply shape and color
database: Database {
  class: storage-cylinder
  class: gpu-memory
}
```

## Color Accessibility

All color combinations achieve **WCAG AA contrast ratio** (4.5:1+) for readability:
- Light fills (#E6F3FF, #FFE6E6, etc.) with dark strokes (#4169E1, #C00000)
- High contrast for text on backgrounds
- Distinguishable by color-blind users (tested with Deuteranopia/Protanopia simulators)

## Maintenance

When adding new style classes:
1. Update `docs/diagrams/src/common/styles.d2`
2. Document in this file with hex codes and use cases
3. Add example to `01_system_overview.d2` legend if it's a primary color
4. Test rendering with `idiag 01` to verify appearance

## See Also

- **Visual Reference**: `docs/diagrams/generated/01_system_overview.svg` (legend at bottom)
- **Style Definitions**: `docs/diagrams/src/common/styles.d2`
- **Layout Config**: `docs/diagrams/src/common/layout-config.json`
- **Rendering Guide**: `docs/diagrams/README.md`
