"""
Test Kroki service for Mermaid diagrams - check if it has better width support
"""
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

print("Testing Kroki service for Mermaid diagrams...\n")

# Test 1: Kroki PNG
print("1. Kroki PNG (default):")
kroki_url = "https://kroki.io/mermaid/png"
headers = {
    'Accept': 'image/png',
    'Content-Type': 'text/plain'
}
try:
    response = requests.post(kroki_url, data=mermaid_code.encode('utf-8'), headers=headers, timeout=15)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        print(f"   ✓ Image size: {img.size[0]}x{img.size[1]} pixels")
        print(f"   File size: {len(response.content):,} bytes")
        img.save("kroki_output.png")
        print(f"   Saved to: kroki_output.png\n")
    else:
        print(f"   ✗ Status: {response.status_code}\n")
except Exception as e:
    print(f"   ✗ Error: {e}\n")

# Test 2: Kroki SVG
print("2. Kroki SVG:")
kroki_svg_url = "https://kroki.io/mermaid/svg"
headers_svg = {
    'Accept': 'image/svg+xml',
    'Content-Type': 'text/plain'
}
try:
    response = requests.post(kroki_svg_url, data=mermaid_code.encode('utf-8'), headers=headers_svg, timeout=15)
    if response.status_code == 200:
        print(f"   ✓ SVG size: {len(response.content):,} bytes")
        with open("kroki_output.svg", "wb") as f:
            f.write(response.content)
        print(f"   Saved to: kroki_output.svg")
        print(f"   (SVG is vector format - scales to any size)\n")
    else:
        print(f"   ✗ Status: {response.status_code}\n")
except Exception as e:
    print(f"   ✗ Error: {e}\n")

print("="*70)
print("Test complete!")
print("="*70)
