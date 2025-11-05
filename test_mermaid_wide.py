"""
Test script with a very wide Mermaid diagram to check actual width limits
"""
import base64
import requests
from PIL import Image
from io import BytesIO

# Create a VERY wide Mermaid diagram
mermaid_code = """
graph LR
    Start[Start Process] --> Step1[Data Collection and Validation]
    Step1 --> Step2[Initial Processing and Transformation]
    Step2 --> Step3[Quality Assurance and Testing Phase]
    Step3 --> Step4[Integration with External Systems]
    Step4 --> Step5[Performance Optimization and Tuning]
    Step5 --> Step6[Security Audit and Compliance Check]
    Step6 --> Step7[User Acceptance Testing and Feedback]
    Step7 --> Step8[Final Deployment and Monitoring]
    Step8 --> End[Process Complete]
"""

print("Testing WIDE Mermaid diagram...\n")

graphbytes = mermaid_code.encode("utf8")
base64_string = base64.urlsafe_b64encode(graphbytes).decode("ascii")

# Test 1: No parameters
print("1. NO parameters:")
url1 = f"https://mermaid.ink/img/{base64_string}"
try:
    response = requests.get(url1, timeout=15)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        print(f"   ✓ Image size: {img.size[0]}x{img.size[1]} pixels")
        print(f"   File size: {len(response.content):,} bytes\n")
    else:
        print(f"   ✗ Status: {response.status_code}\n")
except Exception as e:
    print(f"   ✗ Error: {e}\n")

# Test 2: With width parameter only
print("2. With width=2000:")
url2 = f"https://mermaid.ink/img/{base64_string}?width=2000"
try:
    response = requests.get(url2, timeout=15)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        print(f"   ✓ Image size: {img.size[0]}x{img.size[1]} pixels")
        print(f"   File size: {len(response.content):,} bytes\n")
    else:
        print(f"   ✗ Status: {response.status_code}\n")
except Exception as e:
    print(f"   ✗ Error: {e}\n")

# Test 3: With bgColor to make it easier to see
print("3. With bgColor=white:")
url3 = f"https://mermaid.ink/img/{base64_string}?bgColor=white"
try:
    response = requests.get(url3, timeout=15)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        print(f"   ✓ Image size: {img.size[0]}x{img.size[1]} pixels")
        print(f"   File size: {len(response.content):,} bytes\n")
        
        # Save for inspection
        img.save("test_mermaid_output.png")
        print(f"   Saved to: test_mermaid_output.png\n")
    else:
        print(f"   ✗ Status: {response.status_code}\n")
except Exception as e:
    print(f"   ✗ Error: {e}\n")

# Test 4: SVG format instead of PNG
print("4. SVG format:")
svg_url = f"https://mermaid.ink/svg/{base64_string}"
try:
    response = requests.get(svg_url, timeout=15)
    if response.status_code == 200:
        print(f"   ✓ SVG size: {len(response.content):,} bytes")
        print(f"   Content type: {response.headers.get('Content-Type')}")
        
        # Save SVG
        with open("test_mermaid_output.svg", "wb") as f:
            f.write(response.content)
        print(f"   Saved to: test_mermaid_output.svg\n")
    else:
        print(f"   ✗ Status: {response.status_code}\n")
except Exception as e:
    print(f"   ✗ Error: {e}\n")

print("="*70)
print("Test complete! Check the saved files for visual inspection.")
print("="*70)
