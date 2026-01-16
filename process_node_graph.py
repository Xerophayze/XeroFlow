# process_node_graph.py

import tkinter as tk
from tkinter import messagebox
from formatting_utils import append_formatted_text  # Use append_formatted_text instead of apply_formatting
from node_registry import NODE_REGISTRY  # Ensure node_registry.py is accessible
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
import traceback

def process_node_graph(
    config,
    default_api_details,
    user_input,
    output_box,
    submit_button,
    stop_button,
    stop_event,
    node_graph,
    selected_prompt_name,
    root,
    open_editors,
    gui_queue,
    formatting_enabled,
    chat_tab,  # Added chat_tab parameter
    workflow_id=None,  # Added workflow_id parameter
    on_complete_callback=None,  # Added callback for workflow completion
    on_error_callback=None  # Added callback for workflow errors
):
    """
    Process the node graph with TRUE PARALLEL execution.
    Uses ThreadPoolExecutor to run independent branches simultaneously.
    """
    MAX_WORKERS = 10  # Maximum parallel threads
    MAX_ITERATIONS = 5000  # Safety limit (increased for long-running API calls)

    try:
        if not node_graph:
            return

        nodes = node_graph['nodes']
        connections = node_graph['connections']
        node_lookup = {nid: node for nid, node in nodes.items()}

        # Find the Start Node
        start_nodes = [
            node for node in nodes.values()
            if node.get('properties', {}).get('is_start_node', {}).get('default', False)
        ]
        if len(start_nodes) != 1:
            gui_queue.put(lambda: messagebox.showerror("Error", "There must be exactly one node marked as Start Node."))
            return
        start_node = start_nodes[0]

        print(f"[PARALLEL] Starting workflow with start node ID: {start_node['id']}")

        editor = open_editors.get(selected_prompt_name)
        if editor and editor.is_open():
            gui_queue.put(editor.clear_all_highlights)

        # === BUILD DEPENDENCY GRAPH ===
        # Count how many upstream connections feed into each node
        incoming_connection_count = {}
        for conn in connections:
            to_node_id = conn['to_node']
            incoming_connection_count[to_node_id] = incoming_connection_count.get(to_node_id, 0) + 1

        # === THREAD-SAFE STATE ===
        state_lock = threading.Lock()
        pending_inputs = {}  # node_id -> {input_name: value, '_count': int}
        node_results = {}    # node_id -> output dict
        completed_nodes = set()
        workflow_error = [None]  # Use list to allow modification in nested function
        workflow_complete = threading.Event()
        final_output = [None]

        # Metadata to pass to all nodes
        base_metadata = {
            'gui_queue': gui_queue,
            'parent_window': root,
            'stop_event': stop_event,
            'workflow_id': workflow_id,
            'workflow_name': selected_prompt_name
        }

        def process_single_node(node_id, inputs):
            """Process a single node - runs in thread pool."""
            try:
                if stop_event.is_set():
                    return None, None, []

                node_data = node_lookup.get(node_id)
                if not node_data:
                    raise ValueError(f"Node with ID '{node_id}' not found.")

                # Highlight node
                if editor and editor.is_open():
                    gui_queue.put(lambda nid=node_id: editor.highlight_node(nid))

                # Instantiate and process
                node_type = node_data['type']
                node_class = NODE_REGISTRY.get(node_type)
                if not node_class:
                    raise ValueError(f"No node class registered for type '{node_type}'.")

                node_instance = node_class(node_id=node_id, config=config)
                node_instance.set_properties(node_data)

                print(f"[PARALLEL] Processing node '{node_id}' ({node_type}) with inputs: {[k for k in inputs.keys() if k not in base_metadata]}")
                
                node_output = node_instance.process(inputs)

                print(f"[PARALLEL] Node '{node_id}' completed. Output keys: {list(node_output.keys()) if node_output else 'None'}")

                # Remove highlight
                if editor and editor.is_open():
                    gui_queue.put(lambda nid=node_id: editor.remove_highlight(nid))

                # Check if end node with no connections
                is_end_node = node_instance.properties.get('is_end_node', {}).get('default', False)
                
                # Find downstream nodes
                downstream = []
                if node_output:
                    for output_key, output_value in node_output.items():
                        if not output_value:
                            continue
                        for conn in connections:
                            if conn['from_node'] == node_id and conn['from_output'] == output_key:
                                downstream.append({
                                    'to_node': conn['to_node'],
                                    'to_input': conn.get('to_input', 'input'),
                                    'value': output_value
                                })

                # Track end nodes without downstream connections (no early termination)
                if is_end_node and not downstream:
                    return node_id, node_output, 'END_NODE'
                    
                print(f"[PARALLEL] Node '{node_id}' returning downstream: {len(downstream)} targets: {[d['to_node'] for d in downstream]}")
                return node_id, node_output, downstream

            except Exception as e:
                print(f"[PARALLEL] Error in node '{node_id}': {e}")
                traceback.print_exc()
                return node_id, None, f"ERROR: {e}"

        def submit_ready_nodes(executor, futures):
            """Check pending inputs and submit nodes that are ready to process."""
            nodes_to_submit = []
            
            with state_lock:
                for node_id, pending in list(pending_inputs.items()):
                    expected = incoming_connection_count.get(node_id, 1)
                    received = pending.get('_count', 0)
                    
                    if received >= expected and node_id not in completed_nodes:
                        # Node is ready - prepare inputs
                        inputs = dict(base_metadata)
                        for k, v in pending.items():
                            if k != '_count':
                                inputs[k] = v
                        nodes_to_submit.append((node_id, inputs))
                        del pending_inputs[node_id]

            # Submit outside the lock
            for node_id, inputs in nodes_to_submit:
                print(f"[PARALLEL] Submitting node '{node_id}' for parallel execution")
                future = executor.submit(process_single_node, node_id, inputs)
                futures[future] = node_id

        def deliver_outputs(from_node_id, downstream_list):
            """Deliver outputs to downstream nodes, tracking received counts."""
            with state_lock:
                for item in downstream_list:
                    to_node = item['to_node']
                    to_input = item['to_input']
                    value = item['value']

                    if to_node not in pending_inputs:
                        pending_inputs[to_node] = {'_count': 0}
                    
                    pending_inputs[to_node]['_count'] += 1
                    
                    # Store the input value
                    if to_input in pending_inputs[to_node]:
                        existing = pending_inputs[to_node][to_input]
                        if isinstance(existing, list):
                            existing.append(value)
                        else:
                            pending_inputs[to_node][to_input] = [existing, value]
                    else:
                        pending_inputs[to_node][to_input] = value

                    print(f"[PARALLEL] Delivered output from '{from_node_id}' to '{to_node}' input '{to_input}' (count: {pending_inputs[to_node]['_count']}/{incoming_connection_count.get(to_node, 1)})")

        # === MAIN EXECUTION LOOP ===
        end_node_outputs = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {}
            
            # Start with the start node
            start_inputs = dict(base_metadata)
            start_inputs['input'] = user_input
            
            future = executor.submit(process_single_node, start_node['id'], start_inputs)
            futures[future] = start_node['id']
            
            while True:
                # Check for stop event
                if stop_event.is_set():
                    print("[PARALLEL] Stop event detected, cancelling...")
                    for f in futures:
                        f.cancel()
                    break

                # Check if workflow is complete
                if workflow_complete.is_set():
                    print("[PARALLEL] Workflow complete")
                    break

                # If no futures running, try to submit ready nodes
                if not futures:
                    submit_ready_nodes(executor, futures)
                    if not futures:
                        with state_lock:
                            if not pending_inputs:
                                print("[PARALLEL] All nodes processed, workflow complete")
                                break
                            else:
                                # This shouldn't happen - pending inputs but nothing to run
                                print(f"[PARALLEL] WARNING: Deadlock detected - pending inputs but no futures")
                                for pid, pdata in pending_inputs.items():
                                    print(f"[PARALLEL]   '{pid}': count={pdata.get('_count', 0)}/{incoming_connection_count.get(pid, 1)}")
                                break
                    continue

                # Block until at least one future completes (no timeout = true blocking)
                # Use a reasonable timeout to allow checking stop_event periodically
                future_set = set(futures.keys())
                done, not_done = wait(future_set, timeout=30.0, return_when=FIRST_COMPLETED)

                if not done:
                    # Timeout - check stop event and continue
                    continue

                # Process completed futures
                for future in done:
                    if future not in futures:
                        continue
                    node_id = futures.pop(future)
                    
                    try:
                        result_node_id, output, downstream = future.result()
                        print(f"[PARALLEL] Node '{result_node_id}' completed")
                    except Exception as e:
                        workflow_error[0] = str(e)
                        print(f"[PARALLEL] Node '{node_id}' failed: {e}")
                        traceback.print_exc()
                        continue

                    if output is None and downstream is None:
                        continue

                    if isinstance(downstream, str):
                        if downstream.startswith('ERROR:'):
                            workflow_error[0] = downstream
                            continue
                        elif downstream == 'END_NODE':
                            if output:
                                end_node_outputs.append(output)
                                final_output[0] = next(iter(output.values()))
                                print(f"[PARALLEL] End node output received from '{result_node_id}'")
                            downstream = []

                    with state_lock:
                        completed_nodes.add(result_node_id)
                        if output:
                            node_results[result_node_id] = output

                    # Deliver outputs to downstream nodes
                    if downstream and isinstance(downstream, list):
                        deliver_outputs(result_node_id, downstream)

                # Submit any nodes that are now ready
                submit_ready_nodes(executor, futures)

        # === HANDLE COMPLETION ===
        if stop_event.is_set():
            gui_queue.put(lambda: messagebox.showinfo("Stopped", "Processing has been stopped."))
        elif workflow_error[0]:
            gui_queue.put(lambda err=workflow_error[0]: messagebox.showerror("Error", err))
            if on_error_callback:
                gui_queue.put(lambda err=workflow_error[0]: on_error_callback(err))
        elif final_output[0] is not None or end_node_outputs:
            output_text = final_output[0] if final_output[0] is not None else ''
            gui_queue.put(lambda: [
                setattr(chat_tab, 'response_content', output_text),
                append_formatted_text(output_box, output_text)
            ])
            if on_complete_callback:
                gui_queue.put(lambda out=output_text: on_complete_callback(out))

        # Re-enable buttons
        gui_queue.put(lambda: submit_button.config(state=tk.NORMAL))
        gui_queue.put(lambda: stop_button.config(state=tk.DISABLED))

        if editor and editor.is_open():
            gui_queue.put(editor.clear_all_highlights)

    except Exception as e:
        error_msg = str(e)
        traceback.print_exc()
        gui_queue.put(lambda msg=error_msg: messagebox.showerror("Error", msg))
        gui_queue.put(lambda: submit_button.config(state=tk.NORMAL))
        gui_queue.put(lambda: stop_button.config(state=tk.DISABLED))
        if editor and editor.is_open():
            gui_queue.put(editor.clear_all_highlights)
        if on_error_callback:
            gui_queue.put(lambda msg=error_msg: on_error_callback(msg))
