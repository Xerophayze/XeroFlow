# process_node_graph.py

import tkinter as tk
from tkinter import messagebox
from formatting_utils import append_formatted_text  # Use append_formatted_text instead of apply_formatting
from node_registry import NODE_REGISTRY  # Ensure node_registry.py is accessible
import queue

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
    """Process the node graph and execute the instructions."""
    MAX_ITERATIONS = 500  # Define a reasonable limit to prevent infinite loops
    iteration_count = 0

    try:
        if not node_graph:
            return  # Return if no graph

        # Process the node graph
        nodes = node_graph['nodes']
        connections = node_graph['connections']

        # Create a lookup for nodes by id
        node_lookup = {nid: node for nid, node in nodes.items()}

        # Find the Start Node(s) by checking is_start_node property
        start_nodes = [
            node for node in nodes.values()
            if node.get('properties', {}).get('is_start_node', {}).get('default', False)
        ]
        if len(start_nodes) != 1:
            gui_queue.put(lambda: messagebox.showerror("Error", "There must be exactly one node marked as Start Node (is_start_node set to True)."))
            return
        start_node = start_nodes[0]

        current_node_id = start_node['id']
        input_data = user_input

        print(f"Starting to process the node graph with start node ID: {start_node['id']}")

        # Get the editor if it's open
        editor = open_editors.get(selected_prompt_name)

        # Clear all previous highlights before starting the workflow
        if editor and editor.is_open():
            gui_queue.put(editor.clear_all_highlights)

        # Use a stack to handle nodes and their corresponding input data
        node_stack = [(current_node_id, {
            'input': input_data,
            'gui_queue': gui_queue,
            'parent_window': root,  # Pass the main root window
            'stop_event': stop_event,
            'workflow_id': workflow_id,
            'workflow_name': selected_prompt_name
        })]

        while node_stack:
            # **Check for Stop Event**
            if stop_event.is_set():
                print("Processing has been stopped by the user.")
                gui_queue.put(lambda: messagebox.showinfo("Stopped", "Processing has been stopped."))

                # Re-enable Submit button and disable Stop button
                gui_queue.put(lambda: submit_button.config(state=tk.NORMAL))
                gui_queue.put(lambda: stop_button.config(state=tk.DISABLED))

                # Clear all highlights
                if editor and editor.is_open():
                    gui_queue.put(editor.clear_all_highlights)

                break  # Exit the processing loop

            if iteration_count >= MAX_ITERATIONS:
                gui_queue.put(lambda: messagebox.showerror("Error", "Maximum iterations reached. Possible infinite loop detected."))
                break
            iteration_count += 1

            current_node_id, current_input = node_stack.pop()

            current_node = node_lookup.get(current_node_id)
            if not current_node:
                gui_queue.put(lambda: messagebox.showerror("Error", f"Node with ID '{current_node_id}' not found."))
                return

            # Highlight the current node in the editor if it's open
            if editor and editor.is_open():
                node_id = current_node['id']
                gui_queue.put(lambda nid=node_id: editor.highlight_node(nid))

            # Instantiate the node class based on its type
            node_type = current_node['type']
            node_class = NODE_REGISTRY.get(node_type)
            if not node_class:
                gui_queue.put(lambda: messagebox.showerror("Error", f"No node class registered for type '{node_type}'."))
                return

            # Instantiate the node
            node_instance = node_class(node_id=current_node['id'], config=config)

            # Set node properties
            node_instance.set_properties(current_node)

            # Execute the node's processing logic
            node_output = node_instance.process(current_input)

            print(f"Processed Node '{current_node_id}'. Output: {node_output}")

            # If node_output is None, it indicates workflow termination
            if node_output is None:
                print("Workflow terminated by node")
                # Re-enable Submit button and disable Stop Process button
                gui_queue.put(lambda: submit_button.config(state=tk.NORMAL))
                gui_queue.put(lambda: stop_button.config(state=tk.DISABLED))
                # Clear all highlights
                if editor and editor.is_open():
                    gui_queue.put(editor.clear_all_highlights)
                
                # Mark the workflow as stopped in the workflow manager if workflow_id is provided
                if workflow_id:
                    from main import workflow_manager
                    gui_queue.put(lambda wf_id=workflow_id: workflow_manager.stop_workflow(wf_id))
                    print(f"Marked workflow {workflow_id} as stopped due to node termination")
                
                break

            # **Check if the node is an end node**
            is_end_node = node_instance.properties.get('is_end_node', {}).get('default', False)
            print(f"Node '{current_node_id}' is_end_node: {is_end_node}")
            if is_end_node:
                # Only treat as final output if there are no connections for any outputs
                has_connections = False
                for output_key, output_value in node_output.items():
                    if output_value:  # Only check non-empty outputs
                        connected_nodes = [
                            conn['to_node'] for conn in connections
                            if conn['from_node'] == current_node_id and conn['from_output'] == output_key
                        ]
                        if connected_nodes:
                            has_connections = True
                            break

                if not has_connections:
                    # No connections found, treat this as the final output
                    if node_output:
                        # Get the first output value
                        final_output = next(iter(node_output.values()))
                    else:
                        final_output = 'No input received for final processing.'
                    print(f"[EndNode] Final Output: {final_output}")

                    # Append formatted or plain text based on formatting_enabled
                    gui_queue.put(lambda: [
                        setattr(chat_tab, 'response_content', final_output),
                        append_formatted_text(output_box, final_output)
                    ])

                    # Re-enable Submit button and disable Stop Process button
                    gui_queue.put(lambda: submit_button.config(state=tk.NORMAL))
                    gui_queue.put(lambda: stop_button.config(state=tk.DISABLED))

                    # Call the completion callback if provided
                    if on_complete_callback:
                        gui_queue.put(lambda: on_complete_callback(final_output))

                    # Clear all highlights when the workflow finishes
                    if editor and editor.is_open():
                        gui_queue.put(editor.clear_all_highlights)

                    # Exit the processing loop since it's an end node with no connections
                    break

            # Store the output data back into the node for downstream nodes
            current_node['output_data'] = node_output

            # Create a dictionary to accumulate inputs for each target node
            node_inputs = {}

            # **Handle all outputs from the node**
            found_next_node = False
            for output_key, output_value in node_output.items():
                # **Skip empty outputs**
                if not output_value:
                    print(f"[process_node_graph] Skipping output '{output_key}' as it is empty.")
                    continue

                # Find connections that match this specific output
                matching_connections = [
                    conn for conn in connections
                    if conn['from_node'] == current_node_id and conn['from_output'] == output_key
                ]

                if matching_connections:
                    found_next_node = True
                    for conn in matching_connections:
                        to_node_id = conn['to_node']
                        to_input = conn.get('to_input', 'input')  # Default to 'input' if not specified
                        
                        # Initialize the node's input dictionary if not already done
                        if to_node_id not in node_inputs:
                            node_inputs[to_node_id] = {
                                'gui_queue': gui_queue, 
                                'parent_window': root, # Pass the main root window
                                'stop_event': stop_event, 
                                'workflow_id': workflow_id, 
                                'workflow_name': selected_prompt_name
                            }
                        # If this input already has a value, convert it to a list
                        if to_input in node_inputs[to_node_id]:
                            if isinstance(node_inputs[to_node_id][to_input], list):
                                node_inputs[to_node_id][to_input].append(output_value)
                            else:
                                node_inputs[to_node_id][to_input] = [node_inputs[to_node_id][to_input], output_value]
                        else:
                            node_inputs[to_node_id][to_input] = output_value
                        
                        print(f"[process_node_graph] Sending {output_key} from node '{current_node_id}' to node '{to_node_id}' input '{to_input}'")
                else:
                    # Only show warning if node is not an end node
                    if not is_end_node:
                        print(f"Warning: No next node found for output '{output_key}' of node '{current_node_id}'")

            # Add all nodes with accumulated inputs to the stack
            for to_node_id, inputs in node_inputs.items():
                node_stack.append((to_node_id, inputs))

            if not found_next_node and not is_end_node:
                gui_queue.put(lambda: messagebox.showerror("Error", f"No next node found for outputs of node '{current_node_id}'."))
            
            # Remove highlight from the node after processing
            if editor and editor.is_open():
                gui_queue.put(lambda nid=current_node_id: editor.remove_highlight(nid))

        # Re-enable Submit button and disable Stop Process button
        gui_queue.put(lambda: submit_button.config(state=tk.NORMAL))
        gui_queue.put(lambda: stop_button.config(state=tk.DISABLED))

        # Clear all highlights when the workflow finishes
        if editor and editor.is_open():
            gui_queue.put(editor.clear_all_highlights)

    except Exception as e:
        error_msg = str(e)  # Capture the error message
        gui_queue.put(lambda msg=error_msg: messagebox.showerror("Error", msg))
        # Re-enable Submit button and disable Stop Process button in case of error
        gui_queue.put(lambda: submit_button.config(state=tk.NORMAL))
        gui_queue.put(lambda: stop_button.config(state=tk.DISABLED))
        if editor and editor.is_open():
            gui_queue.put(editor.clear_all_highlights)
        
        # Call the error callback if provided
        if on_error_callback:
            gui_queue.put(lambda: on_error_callback(error_msg))
