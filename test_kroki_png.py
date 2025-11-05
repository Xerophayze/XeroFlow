"""
Test Kroki PNG endpoint to see if it has better resolution than mermaid.ink
"""
import requests
from PIL import Image
from io import BytesIO

print("Testing Kroki PNG vs mermaid.ink PNG")
print("="*70)

# Create a wide Mermaid diagram
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

print("\n1. Testing Kroki PNG endpoint...")
kroki_png_url = "https://kroki.io/mermaid/png"
headers = {
    'Accept': 'image/png',
    'Content-Type': 'text/plain'
}

try:
    response = requests.post(kroki_png_url, data=mermaid_code.encode('utf-8'), headers=headers, timeout=30)
    
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        print(f"   ✓ Kroki PNG: {img.size[0]}x{img.size[1]} pixels")
        print(f"   ✓ File size: {len(response.content):,} bytes")
        
        # Convert to JPEG at 80% quality
        if img.mode != 'RGB':
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = rgb_img
            else:
                img = img.convert('RGB')
        
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=80, optimize=True, progressive=True)
        jpg_bytes = buf.getvalue()
        
        print(f"   ✓ JPEG (80% quality): {len(jpg_bytes):,} bytes")
        
        # Save for inspection
        img.save("kroki_png_output.jpg", format='JPEG', quality=80, optimize=True)
        print(f"   ✓ Saved to: kroki_png_output.jpg")
    else:
        print(f"   ✗ Failed: {response.status_code}")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n2. Testing mermaid.ink PNG endpoint...")
import base64
graphbytes = mermaid_code.encode("utf8")
base64_string = base64.urlsafe_b64encode(graphbytes).decode("ascii")
mermaid_url = f"https://mermaid.ink/img/{base64_string}"

try:
    response = requests.get(mermaid_url, timeout=15)
    
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        print(f"   ✓ mermaid.ink PNG: {img.size[0]}x{img.size[1]} pixels")
        print(f"   ✓ File size: {len(response.content):,} bytes")
        
        # Convert to JPEG at 80% quality
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=80, optimize=True, progressive=True)
        jpg_bytes = buf.getvalue()
        
        print(f"   ✓ JPEG (80% quality): {len(jpg_bytes):,} bytes")
        
        # Save for inspection
        img.save("mermaid_ink_output.jpg", format='JPEG', quality=80, optimize=True)
        print(f"   ✓ Saved to: mermaid_ink_output.jpg")
    else:
        print(f"   ✗ Failed: {response.status_code}")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "="*70)
print("Comparison complete! Check the saved JPEG files.")
print("="*70)
