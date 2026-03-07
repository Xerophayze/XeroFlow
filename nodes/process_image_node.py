# nodes/process_image_node.py
"""ProcessImageNode — accepts an image (file path or URL) plus a text prompt,
sends both to a vision-capable API endpoint, and returns the textual response.

Typical uses:
  - Describe an image
  - Extract text (OCR) from a screenshot
  - Answer questions about a photo
  - Analyse charts, diagrams, or documents in image form
"""

import os
from pathlib import Path
from .base_node import BaseNode
from src.workflows.node_registry import register_node
from services.api_service import APIResponse
from services.token_logger import TokenLogger
from services.pricing_service import PricingService


@register_node('ProcessImageNode')
class ProcessImageNode(BaseNode):
    """Sends an image together with a text prompt to a vision-capable AI
    model and returns the model's textual response.

    Inputs:
      - input  : text prompt / question about the image
      - image  : file path to the image (local path)

    Outputs:
      - output : the AI's textual response about the image

    Properties:
      - api_endpoint : which configured API to use
      - Prompt       : optional system/prepend prompt
      - image_path   : fallback image path if none arrives via the 'image' input
    """

    # -- Node definition ----------------------------------------------------

    def define_inputs(self):
        return ['input', 'image']

    def define_outputs(self):
        return ['output']

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Node Name',
                'default': 'ProcessImageNode',
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': (
                    'Sends an image and a text prompt to a vision-capable AI '
                    'model and returns the textual response. Connect an image '
                    'path to the "image" input and a question/instruction to '
                    'the "input" connector.'
                ),
            },
            'api_endpoint': {
                'type': 'dropdown',
                'label': 'API Endpoint',
                'options': self.get_api_endpoints(),
                'default': self.get_api_endpoints()[0] if self.get_api_endpoints() else '',
            },
            'Prompt': {
                'type': 'textarea',
                'label': 'System / Prepend Prompt',
                'default': '',
            },
            'image_path': {
                'type': 'text',
                'label': 'Image Path (fallback)',
                'default': '',
                'description': (
                    'Local file path to an image. Used only when nothing is '
                    'connected to the "image" input.'
                ),
            },
            'is_start_node': {
                'type': 'boolean',
                'label': 'Start Node',
                'default': False,
            },
            'is_end_node': {
                'type': 'boolean',
                'label': 'End Node',
                'default': False,
            },
        })
        return props

    # -- Processing ---------------------------------------------------------

    def process(self, inputs):
        """Process the image + text through the vision API."""
        print("[ProcessImageNode] Starting process.")

        # --- Resolve the text prompt ---
        user_text = inputs.get('input', '').strip()
        prepend_prompt = (
            self.properties.get('Prompt', {}).get('value')
            or self.properties.get('Prompt', {}).get('default', '')
        ).strip()

        if prepend_prompt and user_text:
            prompt = f"{prepend_prompt}\n\n{user_text}"
        elif prepend_prompt:
            prompt = prepend_prompt
        elif user_text:
            prompt = user_text
        else:
            prompt = "Describe this image in detail."

        print(f"[ProcessImageNode] Prompt: {prompt[:120]}...")

        # --- Resolve the image path ---
        image_input = inputs.get('image', '').strip() if inputs.get('image') else ''
        fallback_path = (
            self.properties.get('image_path', {}).get('value')
            or self.properties.get('image_path', {}).get('default', '')
        ).strip()
        image_path = image_input or fallback_path

        if not image_path:
            error = "No image provided. Connect an image path or set the Image Path property."
            print(f"[ProcessImageNode] Error: {error}")
            return {'output': f"Error: {error}"}

        # Normalise and validate
        image_path = str(Path(image_path))
        if not os.path.isfile(image_path):
            error = f"Image file not found: {image_path}"
            print(f"[ProcessImageNode] Error: {error}")
            return {'output': f"Error: {error}"}

        print(f"[ProcessImageNode] Image: {image_path}")

        # --- Resolve API endpoint ---
        api_name = (
            self.properties.get('api_endpoint', {}).get('value')
            or self.properties.get('api_endpoint', {}).get('default', '')
        )
        if not api_name:
            error = "No API endpoint configured."
            print(f"[ProcessImageNode] Error: {error}")
            return {'output': f"Error: {error}"}

        api_config = self.config.get('interfaces', {}).get(api_name, {})
        model = api_config.get('selected_model')
        max_tokens = api_config.get('max_tokens')
        temperature = api_config.get('temperature')

        print(f"[ProcessImageNode] API: {api_name}, Model: {model}")

        # --- Send the vision request ---
        api_service = self.get_api_service()
        response: APIResponse = api_service.send_vision_request(
            image_path=image_path,
            prompt=prompt,
            api_name=api_name,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if not response.success:
            error = f"API error: {response.error}"
            print(f"[ProcessImageNode] {error}")
            return {'output': f"Error: {error}"}

        # --- Log token usage ---
        if response.total_tokens:
            node_name = self.properties.get('node_name', {}).get('default', 'ProcessImageNode')
            token_usage = {
                'prompt_tokens': response.prompt_tokens,
                'completion_tokens': response.completion_tokens,
                'total_tokens': response.total_tokens,
                'audio_duration': 0,
            }
            pricing_model = response.pricing_model or model
            if not pricing_model:
                pricing_model = 'default'
            TokenLogger.log_token_usage(node_name, api_name, pricing_model, token_usage)

        content = response.content or ""
        print(f"[ProcessImageNode] Response: {len(content)} chars")
        return {'output': content}

    def requires_api_call(self):
        return True
