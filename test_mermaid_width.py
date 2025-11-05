"""
Test script to verify Mermaid diagram width is no longer limited to 768px
"""
import base64
import requests
from PIL import Image
from io import BytesIO

# Sample wide Mermaid diagram
mermaid_code = """
graph LR
    A[Start] --> B[Process 1]
    B --> C[Process 2]
    C --> D[Process 3]
    D --> E[Process 4]
    E --> F[Process 5]
    F --> G[Process 6]
    G --> H[Process 7]
    H --> I[Process 8]
    I --> J[Process 9]
    J --> K[End]
"""

print("Testing Mermaid diagram width limits...\n")

# Test with old parameters (width=1200)
print("1. Testing OLD URL (with width=1200 parameter):")
graphbytes = mermaid_code.encode("utf8")
base64_string = base64.urlsafe_b64encode(graphbytes).decode("ascii")
old_url = f"https://mermaid.ink/img/{base64_string}?scale=2&width=1200"
print(f"   URL: {old_url[:80]}...")

try:
    response = requests.get(old_url, timeout=15)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        print(f"   ✓ Success! Image size: {img.size[0]}x{img.size[1]} pixels")
        print(f"   File size: {len(response.content):,} bytes")
    else:
        print(f"   ✗ Failed with status code: {response.status_code}")
except Exception as e:
    print(f"   ✗ Error: {e}")

print()

# Test with new parameters (scale=2, no width)
print("2. Testing NEW URL (scale=2, no width constraint):")
new_url = f"https://mermaid.ink/img/{base64_string}?scale=2"
print(f"   URL: {new_url[:80]}...")

try:
    response = requests.get(new_url, timeout=15)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        print(f"   ✓ Success! Image size: {img.size[0]}x{img.size[1]} pixels")
        print(f"   File size: {len(response.content):,} bytes")
        
        if img.size[0] > 768:
            print(f"   ✓ Width is greater than 768px - FIX SUCCESSFUL!")
        else:
            print(f"   ⚠ Width is still {img.size[0]}px (may be limited by diagram content)")
    else:
        print(f"   ✗ Failed with status code: {response.status_code}")
except Exception as e:
    print(f"   ✗ Error: {e}")

print()

# Test with no parameters at all
print("3. Testing URL with NO parameters:")
no_param_url = f"https://mermaid.ink/img/{base64_string}"
print(f"   URL: {no_param_url[:80]}...")

try:
    response = requests.get(no_param_url, timeout=15)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        print(f"   ✓ Success! Image size: {img.size[0]}x{img.size[1]} pixels")
        print(f"   File size: {len(response.content):,} bytes")
    else:
        print(f"   ✗ Failed with status code: {response.status_code}")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "="*70)
print("Test complete!")
print("="*70)
