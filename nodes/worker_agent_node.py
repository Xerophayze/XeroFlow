# nodes/worker_agent_node.py
from __future__ import annotations

import json
import time
import copy
import re
from typing import Dict, Any

from .base_node import BaseNode
from src.workflows.node_registry import register_node
from src.database.db_tools import DatabaseManager
from src.workflows.node_registry import NODE_REGISTRY, get_node_catalog
from .agent_comms_channel_node import get_channel


def _safe_db_name(workflow_name: str) -> str:
    if not workflow_name:
        return 'workflow'
    cleaned = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in workflow_name)
    return cleaned.strip('_') or 'workflow'


@register_node('WorkerAgentNode')
class WorkerAgentNode(BaseNode):
    def define_inputs(self):
        return ['input', 'channel_id']

    def define_outputs(self):
        return ['output']

    def define_properties(self):
        props = self.get_default_properties()
        api_endpoints = self.get_api_endpoints()
        default_search_url = self._get_search_api_url_default()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'WorkerAgentNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': (
                    'Headless worker agent for execution tasks and RAG lookup. '
                    'Accepts JSON input with task/query fields and optional tool_calls '
                    '[{"type": "NodeType", "input": "...", "properties": {...}}]. '
                    'Uses inbox_folder/outbox_folder for file I/O context when needed.'
                )
            },
            'agent_id': {
                'type': 'text',
                'label': 'Agent ID',
                'default': 'worker'
            },
            'default_top_k': {
                'type': 'number',
                'label': 'RAG Top K',
                'default': 5,
                'min': 1,
                'max': 20
            },
            'search_api_url': {
                'type': 'text',
                'label': 'Search API URL (SearxNG)',
                'default': default_search_url
            },
            'llm_api_endpoint': {
                'type': 'dropdown',
                'label': 'LLM API Endpoint',
                'options': api_endpoints,
                'default': api_endpoints[0] if api_endpoints else ''
            },
            'llm_model': {
                'type': 'text',
                'label': 'LLM Model (optional)',
                'default': ''
            },
            'llm_temperature': {
                'type': 'number',
                'label': 'LLM Temperature',
                'default': 0.3,
                'min': 0,
                'max': 1
            },
            'enable_llm': {
                'type': 'boolean',
                'label': 'Enable LLM Synthesis',
                'default': True
            },
            'enable_self_reflection': {
                'type': 'boolean',
                'label': 'Enable Self Reflection',
                'default': True
            },
            'max_followup_rounds': {
                'type': 'number',
                'label': 'Max Followup Rounds',
                'default': 1,
                'min': 0,
                'max': 5
            }
        })
        return props

    def process(self, inputs):
        raw_input = inputs.get('input', '')
        channel_id = inputs.get('channel_id')
        agent_id = (
            self.properties.get('agent_id', {}).get('value')
            or self.properties.get('agent_id', {}).get('default')
            or 'worker'
        )
        workflow_name = inputs.get('workflow_name') or inputs.get('workflow_id') or 'workflow'
        inbox_folder = inputs.get('inbox_folder') or ''
        outbox_folder = inputs.get('outbox_folder') or ''
        db_name = _safe_db_name(str(workflow_name))
        top_k = int(
            self.properties.get('default_top_k', {}).get('value')
            or self.properties.get('default_top_k', {}).get('default')
            or 5
        )

        payload: Dict[str, Any]
        if isinstance(raw_input, dict):
            payload = raw_input
        else:
            try:
                payload = json.loads(raw_input) if raw_input else {}
            except Exception:
                payload = {'task': raw_input}

        query = payload.get('query') or payload.get('task') or ''

        tool_results = self._execute_tool_calls(payload.get('tool_calls') or [])
        if tool_results:
            payload['tool_results'] = tool_results

        manager = DatabaseManager()
        manager.ensure_database(db_name)
        results = manager.search(db_name, query, top_k=top_k) if query else []

        # For long queries, also search with a focused excerpt
        # to avoid embedding dilution from verbose task descriptions
        if query and len(query) > 200:
            focused_q = query[:200].rsplit(' ', 1)[0]
            extra = manager.search(db_name, focused_q, top_k=max(2, top_k // 2))
            seen_ids = {r.get('chunk_id') for r in results if r.get('chunk_id')}
            for r in extra:
                if r.get('chunk_id') not in seen_ids:
                    results.append(r)
                    seen_ids.add(r.get('chunk_id'))

        # Search other databases for cross-workflow historical knowledge
        if query and len(results) < top_k:
            try:
                remaining = top_k - len(results)
                for other_db in manager.list_databases():
                    if other_db == db_name:
                        continue
                    other_results = manager.search(other_db, query, top_k=min(remaining, 3))
                    if other_results:
                        results.extend(other_results)
                        remaining = top_k - len(results)
                    if remaining <= 0:
                        break
            except Exception:
                pass

        note_text = payload.get('note') or payload.get('notes') or ''
        if note_text:
            notes = manager.load_notes(db_name)
            agent_notes = notes.get(agent_id, [])
            if isinstance(agent_notes, list):
                agent_notes.append({'timestamp': time.time(), 'note': note_text})
            else:
                agent_notes = [{'timestamp': time.time(), 'note': note_text}]
            notes[agent_id] = agent_notes
            manager.save_notes(db_name, notes)

        channel_messages = []
        if channel_id:
            channel = get_channel(channel_id)
            if channel:
                message = {
                    'type': 'update',
                    'from': agent_id,
                    'message': payload.get('message') or payload.get('task') or 'Worker update',
                    'timestamp': time.time()
                }
                channel.post_message(message)
                channel_messages = channel.snapshot()

        llm_response = self._run_llm_if_enabled(payload, results, tool_results)
        reflection = self._run_self_reflection(payload, results, tool_results, llm_response)
        followup_rounds = 0
        followup_results = []
        while self._has_followups(reflection) and followup_rounds < self._get_max_followup_rounds():
            followup_tasks = reflection.get('followup_tasks', [])
            followup_rounds += 1
            for followup in followup_tasks:
                followup_payload = followup if isinstance(followup, dict) else {'task': str(followup)}
                followup_results.append(
                    self._run_followup_task(
                        followup_payload,
                        workflow_name=workflow_name,
                        channel_id=channel_id,
                        agent_id=agent_id,
                        inbox_folder=inbox_folder,
                        outbox_folder=outbox_folder,
                        top_k=top_k,
                    )
                )
            llm_response = self._run_llm_if_enabled(payload, results, tool_results)
            reflection = self._run_self_reflection(payload, results, tool_results, llm_response)

        # Store meaningful results back into the RAG database for future lookups
        self._store_results_to_rag(manager, db_name, agent_id, query, llm_response, tool_results)

        output_payload = {
            'agent_id': agent_id,
            'workflow': workflow_name,
            'query': query,
            'results': results,
            'notes_saved': bool(note_text),
            'channel_messages': channel_messages,
            'tool_results': tool_results,
            'llm_response': llm_response,
            'inbox_folder': inbox_folder,
            'outbox_folder': outbox_folder,
            'self_reflection': reflection,
            'followup_rounds': followup_rounds,
            'followup_results': followup_results,
            'status': 'ok'
        }
        return {'output': json.dumps(output_payload, indent=2)}

    def _get_search_api_url_default(self) -> str:
        for config in (self.config.get('interfaces') or {}).values():
            if str(config.get('type', '')).lower() == 'searchengine':
                return config.get('api_url') or ''
        return ''

    def _resolve_search_api_url(self) -> str:
        return (
            self.properties.get('search_api_url', {}).get('value')
            or self.properties.get('search_api_url', {}).get('default')
            or ''
        )

    def _resolve_llm_endpoint(self) -> str:
        prop = self.properties.get('llm_api_endpoint', {})
        value = prop.get('value')
        default = prop.get('default')
        raw = value or default or ''
        resolved = self._normalize_endpoint_name(raw)
        print(f"[WorkerAgentNode] _resolve_llm_endpoint: value={value!r}, default={default!r}, raw={raw!r}, resolved={resolved!r}")
        return resolved

    def _normalize_endpoint_name(self, endpoint: str) -> str:
        if not endpoint:
            return ''
        interfaces = self.config.get('interfaces') or {}
        if endpoint in interfaces:
            return endpoint
        lower = endpoint.strip().lower()
        for name in interfaces:
            if name.lower() == lower:
                return name
        tokens = [token for token in re.split(r"\s+", lower) if token]
        best_match = ''
        best_score = 0
        for name in interfaces:
            name_lower = name.lower()
            score = sum(1 for token in tokens if token in name_lower)
            if score > best_score:
                best_score = score
                best_match = name
        return best_match or endpoint

    def _run_llm_if_enabled(self, payload: Dict[str, Any], rag_results: list,
                             tool_results: list) -> str | None:
        enabled = self.properties.get('enable_llm', {}).get('value')
        if enabled is None:
            enabled = self.properties.get('enable_llm', {}).get('default', True)
        if not enabled:
            return None
        instruction = (
            payload.get('llm_prompt')
            or payload.get('instructions')
            or payload.get('task')
            or payload.get('query')
            or ''
        )
        if not instruction:
            return None
        context_blocks = []
        # Include submitted file contents so the worker has the actual
        # document text (passed through from the MCA delegation).
        file_contents = payload.get('file_contents') or []
        if file_contents:
            context_blocks.append(
                "--- SUBMITTED FILE CONTENTS ---\n"
                + "\n\n".join(file_contents)
                + "\n--- END OF SUBMITTED FILES ---"
            )
        if rag_results:
            context_blocks.append(f"RAG Results:\n{json.dumps(rag_results, indent=2)}")
        if tool_results:
            context_blocks.append(f"Tool Results:\n{json.dumps(tool_results, indent=2)}")
        context_text = "\n\n".join(context_blocks)
        from datetime import datetime as _dt
        _now = _dt.now()
        _date_str = _now.strftime('%A, %B %d, %Y')
        _time_str = _now.strftime('%I:%M %p')
        guidance = (
            "You are a Worker Agent with access to a RAG knowledge database and tools (web search/scrape nodes). "
            f"**Current Date & Time:** {_date_str}, {_time_str}\n"
            "IMPORTANT: Always use this date/time when producing documents, reports, or any content that "
            "requires dating. NEVER use dates from your training data.\n\n"
            "IMPORTANT: Always check the RAG Results first — they contain previously gathered research and knowledge. "
            "If the RAG Results already contain the information needed to answer the task, use that data directly "
            "without requesting additional web searches. Only recommend web searches when the RAG data is insufficient "
            "or outdated for the specific question. "
            "If tool_results are provided, use them and do not claim you lack web access. "
            "If the task requires web data and neither RAG nor tool_results have it, report that tools were not "
            "executed and request a rerun with tool_calls."
        )
        base_prompt = instruction if payload.get('llm_prompt') else f"{instruction}\n\n{context_text}".strip()
        prompt = f"{guidance}\n\n{base_prompt}".strip()
        api_endpoint = self._resolve_llm_endpoint()
        if not api_endpoint:
            return None
        model = (
            self.properties.get('llm_model', {}).get('value')
            or self.properties.get('llm_model', {}).get('default')
        )
        temperature = (
            self.properties.get('llm_temperature', {}).get('value')
            or self.properties.get('llm_temperature', {}).get('default')
        )
        print(f"[WorkerAgentNode] _run_llm_if_enabled: sending to api_endpoint={api_endpoint!r}, model={model!r}")
        response = self.send_api_request(prompt, api_endpoint, model=model or None, temperature=temperature)
        if response.success:
            return response.content
        return f"LLM error: {response.error}"

    def _run_self_reflection(self, payload: Dict[str, Any], rag_results: list,
                             tool_results: list, llm_response: str | None) -> dict | None:
        if not self._self_reflection_enabled():
            return None
        instruction = payload.get('task') or payload.get('query') or payload.get('instructions') or ''
        if not instruction:
            return None
        api_endpoint = self._resolve_llm_endpoint()
        if not api_endpoint:
            return None
        from datetime import datetime as _dt
        _now = _dt.now()
        _date_str = _now.strftime('%A, %B %d, %Y')
        _time_str = _now.strftime('%I:%M %p')
        reflection_prompt = (
            "You are a Worker Agent evaluating if your assigned task is complete. "
            f"Current Date & Time: {_date_str}, {_time_str}\n"
            "Return JSON only: {\"completed\": true/false, \"reason\": \"...\", "
            "\"followup_tasks\": [{\"task\": \"...\", \"query\": \"...\", "
            "\"tool_calls\": [{\"type\": \"NodeType\", \"input\": \"...\", \"properties\": {...}}]}]}.\n\n"
            "IMPORTANT RULES:\n"
            "- If you have gathered information and produced a summary or answer, the task IS COMPLETE.\n"
            "- Document export, formatting, Word/Excel/PDF creation are NOT your responsibility — mark complete.\n"
            "- Only add followup_tasks if critical data is MISSING and you have a specific tool_call to get it.\n"
            "- Do NOT add followup_tasks for rephrasing, reformatting, or polishing existing results.\n"
            "- If tool_results contain data (even partial), the task is complete — report what you have.\n"
            "- An empty followup_tasks array means the task is complete.\n\n"
            f"Instruction: {instruction}\n\n"
            f"RAG Results: {json.dumps(rag_results[:3] if len(rag_results) > 3 else rag_results, indent=2)}\n\n"
            f"Tool Results (summary): {len(tool_results)} tool(s) executed\n\n"
            f"Current Summary: {(llm_response or '')[:2000]}"
        )
        response = self.send_api_request(reflection_prompt, api_endpoint, temperature=0.1)
        if not response.success:
            return {'completed': False, 'reason': f"Reflection failed: {response.error}", 'followup_tasks': []}
        return self._extract_json_payload(response.content) or {
            'completed': False,
            'reason': 'Reflection response was not valid JSON.',
            'followup_tasks': []
        }

    def _extract_json_payload(self, response: str) -> dict | None:
        if not response:
            return None
        text = response.strip()
        if text.startswith("```"):
            fence_end = text.rfind("```")
            if fence_end > 0:
                text = text.strip('`').strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None

    def _self_reflection_enabled(self) -> bool:
        enabled = self.properties.get('enable_self_reflection', {}).get('value')
        if enabled is None:
            enabled = self.properties.get('enable_self_reflection', {}).get('default', True)
        return bool(enabled)

    def _get_max_followup_rounds(self) -> int:
        value = (
            self.properties.get('max_followup_rounds', {}).get('value')
            or self.properties.get('max_followup_rounds', {}).get('default')
            or 0
        )
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def _has_followups(self, reflection: dict | None) -> bool:
        if not reflection:
            return False
        followups = reflection.get('followup_tasks')
        return bool(followups)

    def _run_followup_task(self, task_payload: Dict[str, Any], workflow_name: str,
                           channel_id: str | None, agent_id: str, inbox_folder: str,
                           outbox_folder: str, top_k: int) -> Dict[str, Any]:
        query = task_payload.get('query') or task_payload.get('task') or ''
        tool_results = self._execute_tool_calls(task_payload.get('tool_calls') or [])
        manager = DatabaseManager()
        rag_results = manager.search(_safe_db_name(str(workflow_name)), query, top_k=top_k) if query else []
        llm_response = self._run_llm_if_enabled(task_payload, rag_results, tool_results)
        if channel_id:
            channel = get_channel(channel_id)
            if channel:
                channel.post_message({
                    'type': 'update',
                    'from': agent_id,
                    'message': task_payload.get('message') or task_payload.get('task') or 'Worker followup',
                    'timestamp': time.time()
                })
        return {
            'task': task_payload.get('task') or task_payload.get('query'),
            'query': query,
            'tool_results': tool_results,
            'rag_results': rag_results,
            'llm_response': llm_response,
            'status': 'ok'
        }

    def _normalize_tool_properties(self, properties: dict) -> dict:
        if not properties:
            return {}
        normalized = {}
        for key, value in properties.items():
            if not isinstance(key, str):
                normalized[key] = value
                continue
            cleaned = key.strip().lower()
            mapped = {
                'numsearchresults': 'num_search_results',
                'num_results': 'num_search_results',
                'numresultstoskip': 'num_results_to_skip',
                'enablewebsearch': 'enable_web_search',
                'enableurlselection': 'enable_url_selection',
                'searxngapiurl': 'searxng_api_url'
            }.get(cleaned, key)
            normalized[mapped] = value
        return normalized

    def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        results = []
        if not tool_calls:
            return results
        search_api_url = self._resolve_search_api_url()
        llm_endpoint = self._resolve_llm_endpoint()
        print(f"[WorkerAgentNode] _execute_tool_calls: llm_endpoint={llm_endpoint!r}, num_calls={len(tool_calls)}")
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            node_type = call.get('type') or call.get('node_type')
            if not node_type:
                continue
            node_cls = NODE_REGISTRY.get(node_type)
            if not node_cls:
                results.append({'type': node_type, 'status': 'error', 'error': 'Unknown node type'})
                continue
            try:
                node_config = self.config
                if node_type == 'SearchScrapeSummarizeNode' and search_api_url:
                    node_config = copy.deepcopy(self.config)
                    for config in (node_config.get('interfaces') or {}).values():
                        if str(config.get('type', '')).lower() == 'searchengine':
                            config['api_url'] = search_api_url
                node = node_cls(node_id=f"tool_{node_type}", config=node_config)
                properties = self._normalize_tool_properties(call.get('properties') or {})
                valid_endpoints = set((self.config.get('interfaces') or {}).keys())
                if search_api_url and node_type in ('WebSearchNode', 'SearchAndScrapeNode'):
                    properties.setdefault('searxng_api_url', search_api_url)
                if node_type == 'SearchScrapeSummarizeNode':
                    api_endpoint = properties.get('api_endpoint')
                    print(f"[WorkerAgentNode] SearchScrapeSummarize pre-override: api_endpoint={api_endpoint!r}, llm_endpoint={llm_endpoint!r}, valid={llm_endpoint in valid_endpoints if llm_endpoint else 'N/A'}")
                    if llm_endpoint and llm_endpoint in valid_endpoints:
                        properties['api_endpoint'] = llm_endpoint
                    elif api_endpoint and api_endpoint not in valid_endpoints:
                        properties.pop('api_endpoint', None)
                    print(f"[WorkerAgentNode] SearchScrapeSummarize post-override: api_endpoint={properties.get('api_endpoint')!r}")
                if node_type == 'ExportDocumentNode':
                    outbox = (
                        self.properties.get('outbox_folder', {}).get('value')
                        or self.properties.get('outbox_folder', {}).get('default')
                        or ''
                    )
                    if outbox:
                        properties.setdefault('output_folder', outbox)
                for key, value in properties.items():
                    if key in node.properties and isinstance(node.properties[key], dict):
                        node.properties[key]['value'] = value
                    else:
                        node.properties[key] = {'type': 'text', 'default': value, 'value': value}
                tool_input = call.get('input') or call.get('payload') or ''
                output = node.process({'input': tool_input})
                results.append({'type': node_type, 'status': 'ok', 'output': output})
            except Exception as exc:
                results.append({'type': node_type, 'status': 'error', 'error': str(exc)})
        return results

    def _store_results_to_rag(self, manager, db_name: str, agent_id: str,
                              query: str, llm_response: str | None,
                              tool_results: list) -> None:
        """Store meaningful results back into the RAG database for future lookups."""
        try:
            # Store LLM synthesis if it produced a substantive response
            if llm_response and len(llm_response.strip()) > 50:
                source_label = f"worker_{agent_id}_synthesis"
                content = f"Query: {query}\n\nResponse:\n{llm_response}" if query else llm_response
                manager.add_text_content(
                    db_name, content, source_label=source_label,
                    tags=["agent_result", agent_id, "synthesis"]
                )

            # Store successful tool results (e.g. web search summaries)
            for result in (tool_results or []):
                if not isinstance(result, dict) or result.get('status') != 'ok':
                    continue
                output = result.get('output')
                if not output:
                    continue
                # Extract text content from tool output
                text = ''
                if isinstance(output, dict):
                    text = (output.get('summary') or output.get('output')
                            or output.get('prompt') or '')
                    if isinstance(text, dict):
                        text = json.dumps(text)
                elif isinstance(output, str):
                    text = output
                if text and len(text.strip()) > 50:
                    tool_type = result.get('type', 'tool')
                    source_label = f"worker_{agent_id}_{tool_type}"
                    manager.add_text_content(
                        db_name, text, source_label=source_label,
                        tags=["agent_result", agent_id, "tool_output", tool_type]
                    )
        except Exception as exc:
            print(f"[WorkerAgentNode] Warning: failed to store results to RAG: {exc}")

    def _get_tool_catalog_text(self) -> str:
        catalog = get_node_catalog()
        lines = []
        for entry in catalog:
            inputs = ", ".join(entry.get('inputs') or [])
            outputs = ", ".join(entry.get('outputs') or [])
            lines.append(
                f"- {entry.get('type')}: {entry.get('description')} (inputs: {inputs or 'none'}; outputs: {outputs or 'none'})"
            )
        return "\n".join(lines)
