# PlantUML Architecture Diagrams

This directory contains PlantUML source files for the Ionosense HPC architecture documentation.

## Source Files

- `class-architecture.puml` - Complete C++ class hierarchy with design patterns
- `sequence-pipeline.puml` - Asynchronous processing pipeline flow
- `component-architecture.puml` - High-level component relationships
- `memory-management.puml` - Memory layout and data flow patterns

## Generating SVG Files

### Option 1: Online PlantUML Server (Recommended)
1. Copy the contents of any `.puml` file
2. Go to [PlantUML Online Server](http://www.plantuml.com/plantuml/uml/)
3. Paste the content and click "Submit"
4. Download the generated SVG file
5. Save to `docs/diagrams/generated/` with the corresponding name

### Option 2: Local PlantUML Installation

#### Prerequisites
```bash
# Install Java (required for PlantUML)
# Windows: Download from https://adoptium.net/
# Linux: sudo apt install default-jre
# macOS: brew install openjdk

# Install Graphviz (required for PlantUML)
# Windows: Download from https://graphviz.org/download/
# Linux: sudo apt install graphviz
# macOS: brew install graphviz

# Download PlantUML jar
wget http://sourceforge.net/projects/plantuml/files/plantuml.jar/download -O plantuml.jar
```

#### Generate All Diagrams
```bash
# Generate all SVG files
java -jar plantuml.jar -tsvg docs/diagrams/*.puml -o docs/diagrams/generated/

# Generate individual diagram
java -jar plantuml.jar -tsvg docs/diagrams/class-architecture.puml -o docs/diagrams/generated/
```

### Option 3: VS Code Extension
1. Install the "PlantUML" extension by jebbs
2. Open any `.puml` file
3. Press `Ctrl+Shift+P` and run "PlantUML: Export Current Diagram"
4. Select SVG format
5. Save to `docs/diagrams/generated/`

## Diagram Standards

All diagrams follow IEEE publication standards:
- Professional color scheme optimized for print and digital
- Consistent typography and spacing
- Clear notation and legends
- Comprehensive documentation of design patterns

## Integration with Documentation

These diagrams are referenced in:
- `docs/ARCHITECTURE.md` - Main architecture documentation
- `README.md` - Project overview
- API documentation - Implementation details

## Maintenance

When updating the architecture:
1. Modify the corresponding `.puml` source file
2. Regenerate the SVG file using one of the methods above
3. Commit both source and generated files to version control
4. Update any references in the documentation

The source files are the authoritative version - always edit the `.puml` files rather than manually creating diagrams.