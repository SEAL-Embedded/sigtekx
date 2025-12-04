# Publishing SigTekX Placeholder to PyPI

This guide explains how to publish the placeholder v0.0.0 package to claim the "sigtekx" name on PyPI.

## Prerequisites

1. **PyPI Account**: Create account at https://pypi.org/account/register/
2. **TestPyPI Account** (recommended for testing): https://test.pypi.org/account/register/
3. **API Token**: Generate at https://pypi.org/manage/account/#api-tokens

## Setup

### 1. Install Publishing Tools

```bash
# Install/upgrade build and twine
pip install --upgrade build twine
```

### 2. Navigate to Placeholder Directory

```bash
cd pypi-placeholder
```

## Publishing Steps

### Option A: Test on TestPyPI First (Recommended)

```bash
# 1. Build the package
python -m build

# This creates:
# - dist/sigtekx-0.0.0-py3-none-any.whl
# - dist/sigtekx-0.0.0.tar.gz

# 2. Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# When prompted:
# Username: __token__
# Password: <your TestPyPI API token>

# 3. Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ sigtekx

# 4. Verify it works
python -c "import sigtekx; print(sigtekx.__version__)"
# Should print: 0.0.0 and show placeholder message
```

### Option B: Direct to PyPI (Use After Testing)

```bash
# 1. Build the package (if not already done)
python -m build

# 2. Upload to PyPI
python -m twine upload dist/*

# When prompted:
# Username: __token__
# Password: <your PyPI API token>

# 3. Verify on PyPI
# Visit: https://pypi.org/project/sigtekx/

# 4. Test installation
pip install sigtekx
python -c "import sigtekx"
```

## Using API Token

### Save Token in ~/.pypirc (Optional)

Create/edit `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc...YOUR_TOKEN_HERE

[testpypi]
username = __token__
password = pypi-AgENdGVzdC5weXBp...YOUR_TEST_TOKEN_HERE
```

Then upload without password prompt:

```bash
python -m twine upload dist/*  # Uses [pypi] credentials
python -m twine upload --repository testpypi dist/*  # Uses [testpypi] credentials
```

## Verification Checklist

After publishing:

- [ ] Package visible at https://pypi.org/project/sigtekx/
- [ ] `pip install sigtekx` works
- [ ] `import sigtekx` shows placeholder message
- [ ] `sigtekx.__version__` returns `"0.0.0"`
- [ ] README displays correctly on PyPI page
- [ ] Metadata (author, license, classifiers) correct

## Troubleshooting

### Error: "Package already exists"

- Package name is taken! Try a variation or contact PyPI support.
- If you own it, you can't re-upload the same version. Increment version.

### Error: "Invalid credentials"

- Make sure username is exactly `__token__` (with underscores)
- Verify API token is correct and has upload permissions
- Check token hasn't expired

### Error: "File already exists"

- PyPI doesn't allow re-uploading the same version
- Delete `dist/` folder and rebuild, OR
- If you need to fix something, increment version to 0.0.1

### Warning: "Missing metadata"

- Ensure `pyproject.toml` has all required fields
- Check README.md exists and is valid Markdown

## Clean Up

After successful upload:

```bash
# Remove build artifacts
rm -rf dist/ build/ src/*.egg-info
```

## Next Steps

After claiming the name:

1. Complete the full rename (see `../docs/RENAME-TO-SIGTEKX-GUIDE.md`)
2. Build the full package with CUDA components
3. Publish v0.1.0 or v1.0.0 with complete functionality
4. Update PyPI description and metadata

## Security Notes

- **Never commit API tokens** to git!
- Use `.gitignore` to exclude `.pypirc`
- Consider using environment variables for CI/CD:
  ```bash
  export TWINE_USERNAME=__token__
  export TWINE_PASSWORD=<your-token>
  twine upload dist/*
  ```

## Additional Resources

- PyPI Help: https://pypi.org/help/
- Packaging Guide: https://packaging.python.org/
- Twine Docs: https://twine.readthedocs.io/
