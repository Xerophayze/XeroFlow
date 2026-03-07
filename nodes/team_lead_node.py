# nodes/team_lead_node.py
from __future__ import annotations

import json
import time
import uuid
import threading
import queue
import copy
import re
from pathlib import Path
from typing import Dict, Any

from .base_node import BaseNode
from src.workflows.node_registry import register_node
from src.database.db_tools import DatabaseManager
from src.workflows.node_registry import NODE_REGISTRY, get_node_catalog
from .agent_comms_channel_node import get_channel
from .worker_agent_node import WorkerAgentNode


def _safe_db_name(workflow_name: str) -> str:
    if not workflow_name:
        return 'workflow'
    cleaned = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in workflow_name)
    return cleaned.strip('_') or 'workflow'


@register_node('TeamLeadNode')
class TeamLeadNode(BaseNode):
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
                'default': 'TeamLeadNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': (
                    'Headless team lead agent for planning, coordination, and fan-out. '
                    'Accepts JSON input with tasks/delegations and optional tool_calls '
                    '[{"type": "NodeType", "input": "...", "properties": {...}}]. '
                    'Uses RAG search for queries and forwards inbox_folder/outbox_folder to workers.'
                )
            },
            'agent_id': {
                'type': 'text',
                'label': 'Agent ID',
                'default': 'team_lead'
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
            'auto_tool_calls': {
                'type': 'boolean',
                'label': 'Auto Inject Tool Calls',
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
        print(f"[TeamLeadNode] process() ENTERED — code version 2026-02-12-v2")
        raw_input = inputs.get('input', '')
        channel_id = inputs.get('channel_id')
        agent_id = (
            self.properties.get('agent_id', {}).get('value')
            or self.properties.get('agent_id', {}).get('default')
            or 'team_lead'
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
        # Fallback: extract from 'tasks' list (forced delegation format)
        if not query:
            tasks_list = payload.get('tasks') or payload.get('delegations') or []
            parts = []
            for t in (tasks_list if isinstance(tasks_list, list) else [tasks_list]):
                if isinstance(t, dict):
                    parts.append(t.get('task') or t.get('query') or '')
                elif isinstance(t, str):
                    parts.append(t)
            query = ' '.join(p for p in parts if p)
        queries = payload.get('queries') or ([] if not query else [query])

        manager = DatabaseManager()
        manager.ensure_database(db_name)
        all_dbs = manager.list_databases()
        research = []
        for q in queries:
            if q:
                db_results = manager.search(db_name, q, top_k=top_k)
                # For long queries, also search with a focused excerpt
                # to avoid embedding dilution from verbose task descriptions
                if len(q) > 200:
                    focused_q = q[:200].rsplit(' ', 1)[0]
                    extra = manager.search(db_name, focused_q, top_k=max(2, top_k // 2))
                    seen_ids = {r.get('chunk_id') for r in db_results if r.get('chunk_id')}
                    for r in extra:
                        if r.get('chunk_id') not in seen_ids:
                            db_results.append(r)
                            seen_ids.add(r.get('chunk_id'))
                # Search other databases for cross-workflow historical knowledge
                if len(db_results) < top_k:
                    remaining = top_k - len(db_results)
                    for other_db in all_dbs:
                        if other_db == db_name:
                            continue
                        try:
                            other_results = manager.search(other_db, q, top_k=min(remaining, 3))
                            if other_results:
                                db_results.extend(other_results)
                                remaining = top_k - len(db_results)
                            if remaining <= 0:
                                break
                        except Exception:
                            pass
                research.append({
                    'query': q,
                    'results': db_results
                })

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

        if self._should_auto_tool_calls():
            payload = self._inject_tool_calls(payload, top_k)

        channel_messages = []
        if channel_id:
            channel = get_channel(channel_id)
            if channel:
                message = {
                    'type': 'update',
                    'from': agent_id,
                    'message': payload.get('message') or payload.get('task') or 'Team lead update',
                    'timestamp': time.time()
                }
                channel.post_message(message)
                channel_messages = channel.snapshot()

        tool_results = self._execute_tool_calls(payload.get('tool_calls') or [])
        if tool_results:
            payload['tool_results'] = tool_results

        worker_results, task_statuses, completion_summary = self._dispatch_worker_tasks(
            payload=payload,
            channel_id=channel_id,
            workflow_name=workflow_name,
            inbox_folder=inbox_folder,
            outbox_folder=outbox_folder,
        )

        llm_response = self._run_llm_if_enabled(payload, research, tool_results, worker_results)
        reflection = self._run_self_reflection(payload, research, tool_results, worker_results, llm_response)
        followup_rounds = 0
        while self._has_followups(reflection) and followup_rounds < self._get_max_followup_rounds():
            followup_tasks = reflection.get('followup_tasks', [])
            followup_rounds += 1
            more_results, more_statuses, more_summary = self._dispatch_worker_tasks(
                payload={'tasks': followup_tasks},
                channel_id=channel_id,
                workflow_name=workflow_name,
                inbox_folder=inbox_folder,
                outbox_folder=outbox_folder,
            )
            if more_results:
                worker_results.extend(more_results)
            if more_statuses:
                task_statuses.extend(more_statuses)
            completion_summary = self._merge_completion_summaries(completion_summary, more_summary)
            llm_response = self._run_llm_if_enabled(payload, research, tool_results, worker_results)
            reflection = self._run_self_reflection(payload, research, tool_results, worker_results, llm_response)

        # Store TeamLead synthesis back into RAG for future lookups
        self._store_results_to_rag(manager, db_name, agent_id, query, llm_response, tool_results)

        # --- File output post-processing ---
        # If the original task requested file outputs (Word doc, spreadsheet,
        # etc.) and we have an outbox folder, generate those files now.
        created_files = []
        try:
            print(f"[TeamLeadNode] File post-processing: outbox_folder={outbox_folder!r}, llm_response={bool(llm_response)}, llm_len={len(llm_response) if llm_response else 0}")
            if outbox_folder and llm_response:
                created_files = self._generate_requested_files(
                    payload, llm_response, worker_results, outbox_folder,
                    channel_id, agent_id
                )
                print(f"[TeamLeadNode] _generate_requested_files returned {len(created_files)} files: {created_files}")
            else:
                print(f"[TeamLeadNode] Skipping file generation: outbox_folder={bool(outbox_folder)}, llm_response={bool(llm_response)}")
        except Exception as file_exc:
            import traceback
            print(f"[TeamLeadNode] ERROR in file post-processing: {file_exc}")
            traceback.print_exc()

        output_payload = {
            'agent_id': agent_id,
            'workflow': workflow_name,
            'research': research,
            'notes_saved': bool(note_text),
            'channel_messages': channel_messages,
            'tasks': payload.get('tasks', []),
            'worker_results': worker_results,
            'task_statuses': task_statuses,
            'completion_summary': completion_summary,
            'tool_results': tool_results,
            'llm_response': llm_response,
            'inbox_folder': inbox_folder,
            'outbox_folder': outbox_folder,
            'self_reflection': reflection,
            'followup_rounds': followup_rounds,
            'created_files': created_files,
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
        print(f"[TeamLeadNode] _resolve_llm_endpoint: value={value!r}, default={default!r}, raw={raw!r}, resolved={resolved!r}")
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

    def _run_llm_if_enabled(self, payload: Dict[str, Any], research: list,
                             tool_results: list, worker_results: list) -> str | None:
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
        # Fallback: extract from 'tasks' list (forced delegation format)
        if not instruction:
            tasks = payload.get('tasks') or payload.get('delegations') or []
            parts = []
            for t in (tasks if isinstance(tasks, list) else [tasks]):
                if isinstance(t, dict):
                    parts.append(t.get('task') or t.get('query') or t.get('instructions') or '')
                elif isinstance(t, str):
                    parts.append(t)
            instruction = ' '.join(p for p in parts if p)
        if not instruction:
            return None
        context_blocks = []
        # Include submitted file contents so the LLM has the actual
        # document text (passed through from the MCA delegation).
        file_contents = payload.get('file_contents') or []
        if file_contents:
            context_blocks.append(
                "--- SUBMITTED FILE CONTENTS ---\n"
                + "\n\n".join(file_contents)
                + "\n--- END OF SUBMITTED FILES ---"
            )
        if research:
            context_blocks.append(f"Research Results:\n{json.dumps(research, indent=2)}")
        if tool_results:
            context_blocks.append(f"Tool Results:\n{json.dumps(tool_results, indent=2)}")
        if worker_results:
            context_blocks.append(f"Worker Results:\n{json.dumps(worker_results, indent=2)}")
        context_text = "\n\n".join(context_blocks)
        from datetime import datetime as _dt
        _now = _dt.now()
        _date_str = _now.strftime('%A, %B %d, %Y')
        _time_str = _now.strftime('%I:%M %p')
        guidance = (
            "You are a Team Lead Agent with access to a RAG knowledge database and tools (web search/scrape nodes). "
            f"**Current Date & Time:** {_date_str}, {_time_str}\n"
            "IMPORTANT: Always use this date/time when producing documents, reports, or any content that "
            "requires dating. NEVER use dates from your training data.\n\n"
            "Use ALL available data sources to produce the most comprehensive answer:\n"
            "1. Research Results (RAG database) — useful for historical/internal knowledge.\n"
            "2. Tool Results (web searches) — essential for current/updated information.\n"
            "3. Worker Results — synthesized research from your team.\n\n"
            "IMPORTANT: For complex projects involving research, comparisons, or product analysis, "
            "ALWAYS use web search results alongside RAG data. RAG may contain stale or incomplete data. "
            "Combine all sources into a thorough, well-structured synthesis. "
            "If tool_results or worker_results include web data, incorporate that data fully. "
            "Do NOT just repeat RAG data when fresh web search results are available."
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
        response = self.send_api_request(prompt, api_endpoint, model=model or None, temperature=temperature)
        if response.success:
            return response.content
        return f"LLM error: {response.error}"

    def _run_self_reflection(self, payload: Dict[str, Any], research: list,
                             tool_results: list, worker_results: list, llm_response: str | None) -> dict | None:
        if not self._self_reflection_enabled():
            return None
        instruction = payload.get('task') or payload.get('query') or payload.get('instructions') or ''
        if not instruction:
            tasks = payload.get('tasks') or payload.get('delegations') or []
            parts = []
            for t in (tasks if isinstance(tasks, list) else [tasks]):
                if isinstance(t, dict):
                    parts.append(t.get('task') or t.get('query') or t.get('instructions') or '')
                elif isinstance(t, str):
                    parts.append(t)
            instruction = ' '.join(p for p in parts if p)
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
            "You are the Team Lead evaluating if the delegated tasks satisfy the user's request. "
            f"Current Date & Time: {_date_str}, {_time_str}\n"
            "Return JSON only: {\"completed\": true/false, \"reason\": \"...\", "
            "\"followup_tasks\": [{\"task\": \"...\", \"query\": \"...\", "
            "\"tool_calls\": [{\"type\": \"NodeType\", \"input\": \"...\", \"properties\": {...}}]}]}.\n\n"
            "IMPORTANT RULES:\n"
            "- If workers have gathered information and produced results, the task IS COMPLETE.\n"
            "- Document export, formatting, Word/Excel/PDF creation are handled by the caller — mark complete.\n"
            "- Only add followup_tasks if critical data is MISSING and you have a specific tool_call to get it.\n"
            "- Do NOT add followup_tasks for rephrasing, reformatting, polishing, or exporting results.\n"
            "- If some workers had errors but others succeeded with useful data, the task is still complete.\n"
            "- An empty followup_tasks array means the task is complete.\n\n"
            f"Instruction: {instruction}\n\n"
            f"Research queries: {len(research)} completed\n"
            f"Tool Results: {len(tool_results)} tool(s) executed\n"
            f"Worker Results: {len(worker_results)} worker(s) responded\n\n"
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

    def _merge_completion_summaries(self, base: dict, update: dict) -> dict:
        if not base:
            return update or {'total': 0, 'completed': 0, 'errors': 0}
        if not update:
            return base
        total = base.get('total', 0) + update.get('total', 0)
        completed = base.get('completed', 0) + update.get('completed', 0)
        errors = base.get('errors', 0) + update.get('errors', 0)
        completion_rate = completed / total if total else 0.0
        return {
            'total': total,
            'completed': completed,
            'errors': errors,
            'completion_rate': completion_rate
        }

    def _should_auto_tool_calls(self) -> bool:
        enabled = self.properties.get('auto_tool_calls', {}).get('value')
        if enabled is None:
            enabled = self.properties.get('auto_tool_calls', {}).get('default', True)
        return bool(enabled)

    def _inject_tool_calls(self, payload: Dict[str, Any], top_k: int) -> Dict[str, Any]:
        updated = copy.deepcopy(payload) if isinstance(payload, dict) else {'task': str(payload)}
        top_level_text = updated.get('task') or updated.get('query') or ''
        # Fallback: extract from 'tasks' list (forced delegation format)
        if not top_level_text:
            tasks = updated.get('tasks') or updated.get('delegations') or []
            parts = []
            for t in (tasks if isinstance(tasks, list) else [tasks]):
                if isinstance(t, dict):
                    parts.append(t.get('task') or t.get('query') or '')
                elif isinstance(t, str):
                    parts.append(t)
            top_level_text = ' '.join(p for p in parts if p)
        updated['tool_calls'] = self._ensure_tool_calls(updated.get('tool_calls'), top_level_text, top_k)

        tasks = updated.get('tasks') or updated.get('delegations') or []
        if isinstance(tasks, str):
            tasks = [{'task': tasks}]
        new_tasks = []
        for task in tasks:
            if isinstance(task, str):
                task = {'task': task}
            task_tool_calls = self._ensure_tool_calls(task.get('tool_calls'), task.get('task') or task.get('query'), top_k)
            task['tool_calls'] = task_tool_calls
            new_tasks.append(task)
        if new_tasks:
            updated['tasks'] = new_tasks
        return updated

    def _ensure_tool_calls(self, existing: list | None, text: str | None, top_k: int) -> list:
        if existing:
            return existing
        query = (text or '').strip()
        if not query:
            return []
        if not self._needs_web_research(query):
            return []
        tool_type = self._select_tool_type(query)
        if not tool_type:
            return []
        properties = {}
        if tool_type in ('SearchAndScrapeNode', 'SearchScrapeSummarizeNode'):
            properties = {
                'num_search_results': top_k,
                'enable_web_search': True,
                'enable_url_selection': False
            }
        if tool_type == 'WebSearchNode':
            properties = {
                'num_search_results': top_k,
                'num_results_to_skip': 0
            }
        return [{'type': tool_type, 'input': query, 'properties': properties}]

    def _needs_web_research(self, text: str) -> bool:
        lowered = text.lower()
        # Explicit URLs always need web access
        if re.search(r"https?://|www\.", text):
            return True
        # Document creation, formatting, analysis from existing data — no web needed
        if self._is_formatting_only(lowered):
            return False
        # Strong web-search signals (use word boundaries to avoid partial matches)
        strong_keywords = (
            r'\bresearch\b', r'\bweb\s+search\b', r'\bwebsite\b', r'\bonline\b',
            r'\bnews\b', r'\blatest\b', r'\bsearch\s+for\b', r'\bsearch\s+the\b',
            r'\bscrape\b', r'\bcrawl\b', r'\blook\s+up\b', r'\blookup\b',
        )
        if any(re.search(kw, lowered) for kw in strong_keywords):
            return True
        # Weaker signals — only trigger if NOT a knowledge/document task
        weak_keywords = (
            r'\bfind\b', r'\bcompare\b', r'\bverify\b', r'\bsource\b',
            r'\bsources\b', r'\breference\b', r'\blink\b', r'\burls\b',
        )
        if any(re.search(kw, lowered) for kw in weak_keywords):
            # If the task is primarily about creating/writing/analysing
            # documents from existing knowledge, skip web search
            knowledge_terms = (
                'create', 'write', 'draft', 'compose', 'make', 'build',
                'document', 'report', 'spreadsheet', 'word doc', 'docx',
                'excel', 'csv', 'template', 'letter', 'memo', 'proposal',
                'analyse', 'analyze', 'summarize', 'summary', 'review',
                'explain', 'describe', 'outline', 'plan', 'list',
                'transcript', 'based on', 'from the', 'using the',
            )
            if any(term in lowered for term in knowledge_terms):
                return False
            return True
        return False

    def _is_formatting_only(self, lowered: str) -> bool:
        format_terms = (
            'format', 'write', 'draft', 'compose', 'blog', 'breakdown', 'summary',
            'summarize', 'report', 'outline', 'structure', 'create', 'make',
            'build', 'template', 'letter', 'memo', 'proposal', 'document',
            'spreadsheet', 'word doc', 'docx', 'excel', 'csv', 'analyse',
            'analyze', 'review', 'explain', 'describe', 'transcript',
        )
        if not any(term in lowered for term in format_terms):
            return False
        search_verbs = (
            'search', 'look up', 'lookup', 'gather from web', 'collect from web',
            'scrape', 'crawl', 'research online', 'web search', 'search online',
        )
        return not any(term in lowered for term in search_verbs)

    def _select_tool_type(self, text: str) -> str | None:
        lowered = text.lower()
        if 'searchscrapesummarize' in lowered:
            return 'SearchScrapeSummarizeNode'
        if 'searchandscrape' in lowered:
            return 'SearchAndScrapeNode'
        if 'websearch' in lowered:
            return 'WebSearchNode'
        if 'webscraping' in lowered:
            return 'WebScrapingNode'
        if re.search(r"https?://|www\.", text) or 'scrape' in lowered:
            return 'WebScrapingNode'
        if any(term in lowered for term in ('news', 'headline', 'headlines', 'article', 'articles')):
            return 'SearchScrapeSummarizeNode'
        if any(term in lowered for term in ('summarize', 'summary', 'overview', 'report')):
            return 'SearchScrapeSummarizeNode'
        if any(term in lowered for term in ('list', 'urls', 'links')):
            return 'WebSearchNode'
        return 'SearchAndScrapeNode'

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

    # ------------------------------------------------------------------
    # File output post-processing
    # ------------------------------------------------------------------

    def _detect_requested_file_outputs(self, payload: Dict[str, Any]) -> list[dict]:
        """Analyse the original task to determine what files the user wants.

        Returns a list of dicts like:
            [{"format": "word", "topic": "sales info", "filename": "sales_info"},
             {"format": "excel", "topic": "cost tracking", "filename": "cost_tracking"}]
        """
        task_text = (
            payload.get('task') or payload.get('query')
            or payload.get('instructions') or ''
        )
        # Also check the 'tasks' list — the forced delegation sends
        # {"tasks": [{"task": "..."}]} rather than a top-level "task" key.
        # NOTE: Do NOT fall back to payload['message'] here — it contains
        # delegation metadata, not the user's actual request.
        if not task_text:
            tasks = payload.get('tasks') or payload.get('delegations') or []
            parts = []
            for t in (tasks if isinstance(tasks, list) else [tasks]):
                if isinstance(t, dict):
                    parts.append(t.get('task') or t.get('query') or t.get('instructions') or '')
                elif isinstance(t, str):
                    parts.append(t)
            task_text = ' '.join(p for p in parts if p)
        task_text = task_text.lower()
        print(f"[TeamLeadNode] _detect_requested_file_outputs: task_text length={len(task_text)}, first 120={task_text[:120]!r}")
        if not task_text:
            print("[TeamLeadNode] _detect_requested_file_outputs: no task text found — skipping")
            return []

        # Quick check: does the task mention any output file types?
        file_keywords = (
            'word document', 'word doc', 'docx', '.docx',
            'spreadsheet', 'excel', '.xlsx', 'xls',
            'csv', '.csv',
            'text file', '.txt',
            'document', 'file', 'report',
        )
        if not any(kw in task_text for kw in file_keywords):
            return []

        # Use the LLM to parse the task and identify requested files
        api_endpoint = self._resolve_llm_endpoint()
        if not api_endpoint:
            return []

        parse_prompt = (
            "Analyse the following task and identify what output files the user wants created. "
            "Return ONLY a JSON array. Each element must have:\n"
            '  - "format": one of "word", "excel", "csv", "text"\n'
            '  - "topic": brief description of what the file should contain\n'
            '  - "filename": a short snake_case filename (no extension)\n\n'
            "If the task does NOT request any file outputs, return an empty array: []\n\n"
            "Rules:\n"
            '- "word document", "document", "doc", "docx", "report" → format "word"\n'
            '- "spreadsheet", "excel", "xlsx", "xls", "tracking sheet" → format "excel"\n'
            '- "csv" → format "csv"\n'
            '- "text file", "txt" → format "text"\n\n'
            f"Task: {task_text}\n\n"
            "JSON array:"
        )
        response = self.send_api_request(parse_prompt, api_endpoint, temperature=0.1)
        if not response.success:
            return []

        # Parse the JSON array from the response
        text = response.content.strip()
        # Strip markdown fences if present
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:])
            if text.rstrip().endswith('```'):
                text = text.rstrip()[:-3].rstrip()
        start = text.find('[')
        end = text.rfind(']')
        if start == -1 or end == -1:
            return []
        try:
            files = json.loads(text[start:end + 1])
            if not isinstance(files, list):
                return []
            # Validate each entry
            valid = []
            for f in files:
                if isinstance(f, dict) and f.get('format') and f.get('filename'):
                    fmt = f['format'].lower()
                    if fmt in ('word', 'excel', 'csv', 'text'):
                        valid.append({
                            'format': fmt,
                            'topic': f.get('topic', ''),
                            'filename': f['filename'],
                        })
            return valid
        except (json.JSONDecodeError, Exception):
            return []

    def _format_content_for_file(self, file_spec: dict, llm_response: str,
                                  worker_results: list,
                                  api_endpoint: str,
                                  user_request: str = '',
                                  file_contents: list = None) -> str | None:
        """Ask the LLM to produce properly formatted content for a specific
        output file, using the synthesis and worker results as source data."""
        fmt = file_spec['format']
        topic = file_spec.get('topic', '')

        # Collect worker LLM responses as source material
        source_blocks = []
        # Include the actual submitted file contents first — these are the
        # primary source documents the user uploaded.
        if file_contents:
            source_blocks.append(
                "--- SUBMITTED FILE CONTENTS (primary source documents) ---\n"
                + "\n\n".join(file_contents)
                + "\n--- END OF SUBMITTED FILES ---"
            )
        if llm_response:
            source_blocks.append(f"Team Lead Synthesis:\n{llm_response}")
        for wr in (worker_results or []):
            if isinstance(wr, dict):
                wr_resp = wr.get('llm_response') or ''
                if wr_resp:
                    wid = wr.get('worker_id', 'worker')
                    source_blocks.append(f"Worker {wid} response:\n{wr_resp}")
        source_text = "\n\n".join(source_blocks)
        # Truncate to avoid blowing context
        if len(source_text) > 16000:
            source_text = source_text[:16000] + "\n... (truncated)"

        if fmt == 'excel':
            format_instruction = (
                "Produce the content as GitHub-flavoured markdown tables.\n"
                "STRICT TABLE FORMATTING RULES:\n"
                "- Every table row (header, separator, and data) MUST start AND end with a pipe character |.\n"
                "- Each row MUST be on a single line — never wrap or break a row across multiple lines.\n"
                "- Include a separator row (e.g., | --- | --- |) immediately after the header row.\n"
                "- All data rows MUST have the same number of columns as the header. Use empty cells (| |) for blanks.\n"
                "- Formulas start with = (e.g., =B2+C2). NEVER wrap formulas in quotes.\n"
                "- If multiple tables/sheets are needed, separate them with markdown headings (## Sheet Name).\n"
                "- Use <pbreak> on its own line between sections that should be separate Excel sheets.\n"
                "- Do NOT repeat table data as narrative text — output ONLY the markdown tables with optional headings.\n"
                "The output will be converted directly to an Excel spreadsheet."
            )
        elif fmt == 'csv':
            format_instruction = (
                "Produce the content as comma-separated values (CSV format). "
                "Include a header row. The output will be saved as a .csv file."
            )
        elif fmt == 'text':
            format_instruction = (
                "Produce the content as clean plain text. "
                "The output will be saved as a .txt file."
            )
        else:  # word
            format_instruction = (
                "Produce the content as well-formatted markdown with headings, "
                "paragraphs, bold/italic emphasis, bullet lists, and tables where "
                "appropriate. The output will be converted to a Word document (.docx). "
                "Make it professional and well-structured."
            )

        # Build the prompt — user's original request is the PRIMARY specification
        user_req_block = ''
        if user_request:
            user_req_block = (
                f"USER'S ORIGINAL REQUEST (this is the PRIMARY specification — follow it closely):\n"
                f"{user_request}\n\n"
            )
        from datetime import datetime as _dt
        _now = _dt.now()
        _date_str = _now.strftime('%A, %B %d, %Y')
        _time_str = _now.strftime('%I:%M %p')
        content_prompt = (
            f"You are producing content for a {fmt} file.\n"
            f"**Current Date & Time:** {_date_str}, {_time_str}\n"
            "IMPORTANT: Use this date/time for any dates in the document. "
            "NEVER use dates from your training data.\n\n"
            f"Topic/purpose: {topic}\n\n"
            f"{user_req_block}"
            f"{format_instruction}\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "- The USER'S ORIGINAL REQUEST above is your primary guide. Follow its requirements closely.\n"
            "- The Source data below is supplementary reference — do NOT just copy or lightly edit it.\n"
            "- If the user asks for something detailed/complex, produce detailed/complex output.\n"
            "- Generate FRESH content that fully satisfies the user's request, even if the source data is simpler.\n"
            "- Output ONLY the file content — no commentary, no preamble, no summary at the end.\n\n"
            f"Source data (reference only):\n{source_text}\n\n"
            "File content:"
        )
        response = self.send_api_request(content_prompt, api_endpoint, temperature=0.2)
        if response.success and response.content and response.content.strip():
            return response.content.strip()
        return None

    def _generate_requested_files(self, payload: Dict[str, Any],
                                   llm_response: str,
                                   worker_results: list,
                                   outbox_folder: str,
                                   channel_id: str | None,
                                   agent_id: str) -> list[dict]:
        """Detect requested file outputs, generate content, and write files
        to the outbox folder using ExportDocumentNode.

        Returns a list of dicts: [{"path": "...", "format": "...", "filename": "..."}]
        """
        import os
        requested = self._detect_requested_file_outputs(payload)
        if not requested:
            return []

        # Create a unique project subfolder under the outbox
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_name = payload.get('project_name') or 'Project'
        # Sanitise for filesystem
        safe_name = re.sub(r'[^\w\s-]', '', proj_name).strip().replace(' ', '_') or 'Project'
        project_id = f"{safe_name}_{ts}_{uuid.uuid4().hex[:6]}"
        project_folder = os.path.join(outbox_folder, project_id)
        os.makedirs(project_folder, exist_ok=True)
        print(f"[TeamLeadNode] Created project folder: {project_folder}")

        api_endpoint = self._resolve_llm_endpoint()
        created_files = []

        # --- Copy original source files into the project folder ---
        source_file_paths = payload.get('source_file_paths') or []
        if source_file_paths:
            import shutil
            source_dir = os.path.join(project_folder, "source_files")
            os.makedirs(source_dir, exist_ok=True)
            for src_path_str in source_file_paths:
                src_path = Path(src_path_str)
                if src_path.exists() and src_path.is_file():
                    try:
                        shutil.copy2(str(src_path), os.path.join(source_dir, src_path.name))
                        print(f"[TeamLeadNode] Copied source file: {src_path.name}")
                    except Exception as copy_exc:
                        print(f"[TeamLeadNode] Could not copy {src_path.name}: {copy_exc}")

        # Grab submitted file contents for the content generator
        file_contents = payload.get('file_contents') or []

        # Extract the user's original request to pass to the content generator
        user_request_text = (
            payload.get('task') or payload.get('query')
            or payload.get('instructions') or ''
        )
        if not user_request_text:
            tasks = payload.get('tasks') or payload.get('delegations') or []
            parts = []
            for t in (tasks if isinstance(tasks, list) else [tasks]):
                if isinstance(t, dict):
                    parts.append(t.get('task') or t.get('query') or t.get('instructions') or '')
                elif isinstance(t, str):
                    parts.append(t)
            user_request_text = ' '.join(p for p in parts if p)

        for file_spec in requested:
            fmt = file_spec['format']
            filename = file_spec['filename']
            topic = file_spec.get('topic', '')

            print(f"[TeamLeadNode] Generating {fmt} file: {filename} — {topic}")

            # Get properly formatted content from LLM
            content = self._format_content_for_file(
                file_spec, llm_response, worker_results, api_endpoint,
                user_request=user_request_text,
                file_contents=file_contents,
            )
            if not content:
                print(f"[TeamLeadNode] Failed to generate content for {filename}")
                continue

            # Use ExportDocumentNode to write the file
            try:
                from .export_document_node import ExportDocumentNode
                export_node = ExportDocumentNode(
                    node_id=f"export_{filename}", config=self.config
                )
                # Map format to ExportDocumentNode format string
                format_map = {
                    'word': 'Word (.docx)',
                    'excel': 'Excel (.xlsx)',
                    'csv': 'Text (.txt)',  # CSV handled as text
                    'text': 'Text (.txt)',
                }
                export_format = format_map.get(fmt, 'Word (.docx)')

                # For CSV, write directly instead of using ExportDocumentNode
                if fmt == 'csv':
                    import datetime
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    csv_path = os.path.join(project_folder, f"{filename}_{ts}.csv")
                    with open(csv_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    if os.path.exists(csv_path):
                        created_files.append({
                            'path': csv_path,
                            'format': 'csv',
                            'filename': filename,
                        })
                        print(f"[TeamLeadNode] Created CSV: {csv_path}")
                    continue

                # Set properties for ExportDocumentNode
                export_node.properties['export_format'] = {
                    'type': 'dropdown', 'value': export_format
                }
                export_node.properties['output_folder'] = {
                    'type': 'folder', 'value': project_folder
                }
                export_node.properties['filename'] = {
                    'type': 'text', 'value': filename
                }
                export_node.properties['append_timestamp'] = {
                    'type': 'boolean', 'value': True
                }
                export_node.properties['formatting_enabled'] = {
                    'type': 'boolean', 'value': True
                }
                export_node.properties['auto_open'] = {
                    'type': 'boolean', 'value': False
                }

                result = export_node.process({'input': content})
                output_msg = result.get('output', '')
                if 'Successfully exported to:' in output_msg:
                    file_path = output_msg.split('Successfully exported to:')[1].strip()
                    created_files.append({
                        'path': file_path,
                        'format': fmt,
                        'filename': filename,
                    })
                    print(f"[TeamLeadNode] Created {fmt} file: {file_path}")
                else:
                    print(f"[TeamLeadNode] Export failed for {filename}: {output_msg}")

            except Exception as exc:
                print(f"[TeamLeadNode] Error creating {filename}: {exc}")

        # Post file creation status to comms channel
        if created_files and channel_id:
            channel = get_channel(channel_id)
            if channel:
                file_list = ", ".join(
                    f"{f['filename']}.{f['format']}" for f in created_files
                )
                channel.post_message({
                    'type': 'file_created',
                    'from': agent_id,
                    'message': f"Created {len(created_files)} file(s): {file_list}",
                    'files': created_files,
                    'timestamp': time.time(),
                })

        return created_files

    def _dispatch_worker_tasks(self, payload: Dict[str, Any], channel_id: str | None,
                               workflow_name: str, inbox_folder: str,
                               outbox_folder: str) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]], dict]:
        tasks = payload.get('tasks') or payload.get('delegations') or []
        if isinstance(tasks, str):
            tasks = [tasks]
        if not tasks:
            return [], [], {'total': 0, 'completed': 0, 'errors': 0}

        task_queue: queue.Queue = queue.Queue()
        status_lock = threading.Lock()
        results: list[Dict[str, Any]] = []
        task_statuses: list[Dict[str, Any]] = []

        # Forward submitted file contents to each worker so they have
        # the actual document text for their analysis tasks.
        parent_file_contents = payload.get('file_contents') or []

        for task in tasks:
            task_payload = task if isinstance(task, dict) else {'task': str(task)}
            # Inject file contents into each worker's task payload
            if parent_file_contents and 'file_contents' not in task_payload:
                task_payload['file_contents'] = parent_file_contents
            task_id = task_payload.get('task_id') or str(uuid.uuid4())[:8]
            worker_id = task_payload.get('agent_id') or f"worker_{uuid.uuid4().hex[:8]}"
            task_queue.put((task_id, worker_id, task_payload))
            task_statuses.append({
                'task_id': task_id,
                'worker_id': worker_id,
                'status': 'queued',
                'score': 0.0,
                'error': None
            })

        def update_status(task_id: str, status: str, score: float | None = None, error: str | None = None):
            with status_lock:
                for entry in task_statuses:
                    if entry['task_id'] == task_id:
                        entry['status'] = status
                        if score is not None:
                            entry['score'] = score
                        if error is not None:
                            entry['error'] = error
                        break

        def post_channel(status_payload: dict):
            if not channel_id:
                return
            channel = get_channel(channel_id)
            if channel:
                channel.post_message(status_payload)

        def worker_loop():
            while True:
                try:
                    task_id, worker_id, task_payload = task_queue.get_nowait()
                except queue.Empty:
                    return
                update_status(task_id, 'running')
                post_channel({
                    'type': 'worker_status',
                    'from': worker_id,
                    'task_id': task_id,
                    'status': 'running',
                    'timestamp': time.time()
                })
                try:
                    result = self._run_worker_task(
                        task_payload,
                        worker_id,
                        channel_id,
                        workflow_name,
                        inbox_folder,
                        outbox_folder,
                    )
                    results.append(result)
                    score = 1.0 if result else 0.0
                    update_status(task_id, 'completed', score=score)
                    post_channel({
                        'type': 'worker_status',
                        'from': worker_id,
                        'task_id': task_id,
                        'status': 'completed',
                        'score': score,
                        'timestamp': time.time()
                    })
                except Exception as exc:
                    update_status(task_id, 'error', score=0.0, error=str(exc))
                    results.append({'status': 'error', 'error': str(exc), 'worker_id': worker_id})
                    post_channel({
                        'type': 'worker_status',
                        'from': worker_id,
                        'task_id': task_id,
                        'status': 'error',
                        'error': str(exc),
                        'timestamp': time.time()
                    })
                finally:
                    task_queue.task_done()

        threads = []
        for _ in range(len(tasks)):
            thread = threading.Thread(target=worker_loop, daemon=True)
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        completed = sum(1 for entry in task_statuses if entry['status'] == 'completed')
        errors = sum(1 for entry in task_statuses if entry['status'] == 'error')
        completion_summary = {
            'total': len(task_statuses),
            'completed': completed,
            'errors': errors,
            'completion_rate': completed / len(task_statuses) if task_statuses else 0.0
        }

        return results, task_statuses, completion_summary

    def _run_worker_task(self, task_payload: Dict[str, Any], worker_id: str,
                         channel_id: str | None, workflow_name: str,
                         inbox_folder: str, outbox_folder: str) -> Dict[str, Any]:
        worker = WorkerAgentNode(node_id=f"worker_{worker_id}", config=self.config)
        worker.properties.setdefault('agent_id', {'type': 'text', 'default': worker_id})
        worker.properties['agent_id']['value'] = worker_id
        llm_endpoint = self._resolve_llm_endpoint()
        print(f"[TeamLeadNode] _run_worker_task: propagating llm_endpoint={llm_endpoint!r} to worker {worker_id}")
        if llm_endpoint:
            worker.properties.setdefault('llm_api_endpoint', {'type': 'dropdown', 'default': llm_endpoint})
            worker.properties['llm_api_endpoint']['value'] = llm_endpoint
        llm_model = (
            self.properties.get('llm_model', {}).get('value')
            or self.properties.get('llm_model', {}).get('default')
        )
        if llm_model:
            worker.properties.setdefault('llm_model', {'type': 'text', 'default': llm_model})
            worker.properties['llm_model']['value'] = llm_model
        llm_temperature = (
            self.properties.get('llm_temperature', {}).get('value')
            or self.properties.get('llm_temperature', {}).get('default')
        )
        if llm_temperature is not None:
            worker.properties.setdefault('llm_temperature', {'type': 'number', 'default': llm_temperature})
            worker.properties['llm_temperature']['value'] = llm_temperature
        search_api_url = self._resolve_search_api_url()
        if search_api_url:
            worker.properties.setdefault('search_api_url', {'type': 'text', 'default': search_api_url})
            worker.properties['search_api_url']['value'] = search_api_url
        if outbox_folder:
            worker.properties.setdefault('outbox_folder', {'type': 'folder', 'default': outbox_folder})
            worker.properties['outbox_folder']['value'] = outbox_folder
        worker_inputs = {
            'input': task_payload,
            'channel_id': channel_id,
            'workflow_name': workflow_name,
            'inbox_folder': inbox_folder,
            'outbox_folder': outbox_folder,
        }
        result = worker.process(worker_inputs)
        output = result.get('output') if isinstance(result, dict) else result
        try:
            parsed = json.loads(output) if isinstance(output, str) else output
        except Exception:
            parsed = {'raw_output': output}
        parsed['worker_id'] = worker_id
        return parsed

    def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        results = []
        if not tool_calls:
            return results
        search_api_url = self._resolve_search_api_url()
        llm_endpoint = self._resolve_llm_endpoint()
        print(f"[TeamLeadNode] _execute_tool_calls: llm_endpoint={llm_endpoint!r}, num_calls={len(tool_calls)}")
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
                    print(f"[TeamLeadNode] SearchScrapeSummarize pre-override: api_endpoint={api_endpoint!r}, llm_endpoint={llm_endpoint!r}, valid={llm_endpoint in valid_endpoints if llm_endpoint else 'N/A'}")
                    if llm_endpoint and llm_endpoint in valid_endpoints:
                        properties['api_endpoint'] = llm_endpoint
                    elif api_endpoint and api_endpoint not in valid_endpoints:
                        properties.pop('api_endpoint', None)
                    print(f"[TeamLeadNode] SearchScrapeSummarize post-override: api_endpoint={properties.get('api_endpoint')!r}")
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
            if llm_response and len(llm_response.strip()) > 50:
                source_label = f"teamlead_{agent_id}_synthesis"
                content = f"Query: {query}\n\nResponse:\n{llm_response}" if query else llm_response
                manager.add_text_content(
                    db_name, content, source_label=source_label,
                    tags=["agent_result", agent_id, "synthesis"]
                )

            for result in (tool_results or []):
                if not isinstance(result, dict) or result.get('status') != 'ok':
                    continue
                output = result.get('output')
                if not output:
                    continue
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
                    source_label = f"teamlead_{agent_id}_{tool_type}"
                    manager.add_text_content(
                        db_name, text, source_label=source_label,
                        tags=["agent_result", agent_id, "tool_output", tool_type]
                    )
        except Exception as exc:
            print(f"[TeamLeadNode] Warning: failed to store results to RAG: {exc}")

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
