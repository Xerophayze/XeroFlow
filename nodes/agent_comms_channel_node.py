# nodes/agent_comms_channel_node.py
from __future__ import annotations

import threading
import time
from typing import Dict, List

from .base_node import BaseNode
from src.workflows.node_registry import register_node


class AgentChannel:
    def __init__(self, channel_id: str, workflow_id: str, name: str):
        self.channel_id = channel_id
        self.workflow_id = workflow_id
        self.name = name
        self._lock = threading.Lock()
        self._messages: List[Dict] = []

    def post_message(self, message: Dict) -> None:
        with self._lock:
            self._messages.append(message)

    def snapshot(self) -> List[Dict]:
        with self._lock:
            return list(self._messages)


_CHANNELS: Dict[str, AgentChannel] = {}
_CHANNEL_LOCK = threading.Lock()


def create_channel(workflow_id: str, name: str) -> AgentChannel:
    channel_id = f"{workflow_id}:{name}"
    with _CHANNEL_LOCK:
        channel = _CHANNELS.get(channel_id)
        if not channel:
            channel = AgentChannel(channel_id, workflow_id, name)
            _CHANNELS[channel_id] = channel
    return channel


def get_channel(channel_id: str) -> AgentChannel | None:
    with _CHANNEL_LOCK:
        return _CHANNELS.get(channel_id)


@register_node('AgentCommsChannelNode')
class AgentCommsChannelNode(BaseNode):
    def define_inputs(self):
        return []

    def define_outputs(self):
        return ['channel_id']

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'AgentCommsChannelNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': (
                    'Creates a per-workflow in-memory comms channel for agents. '
                    'Returns channel_id; pass it into TeamLead/Worker inputs to post status '
                    'updates and coordination messages.'
                )
            },
            'channel_name': {
                'type': 'text',
                'label': 'Channel Name',
                'default': 'team'
            }
        })
        return props

    def process(self, inputs):
        workflow_id = inputs.get('workflow_id') or inputs.get('workflow_name') or 'workflow'
        channel_name = (
            self.properties.get('channel_name', {}).get('value')
            or self.properties.get('channel_name', {}).get('default')
            or 'team'
        )
        channel = create_channel(str(workflow_id), str(channel_name))
        channel.post_message({
            'type': 'system',
            'from': 'channel',
            'message': f"Channel '{channel.name}' initialized.",
            'timestamp': time.time()
        })
        return {'channel_id': channel.channel_id}
