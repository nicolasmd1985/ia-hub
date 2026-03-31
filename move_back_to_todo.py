#!/usr/bin/env python3
import mission_control
import json

def move_back_to_todo():
    env = mission_control.load_env()
    token = env.get("GITHUB_TOKEN")
    owner = env.get("GITHUB_USER")
    number = int(env.get("PROJECT_NUMBER", "2"))

    # 1. Fetch all items (not just Todo)
    res = mission_control.query_graphql(mission_control.GET_PROJECT_ITEMS, {"owner": owner, "number": number}, token)
    if not res or "data" not in res:
        print("Failed to fetch project data.")
        return

    project = res["data"]["user"]["projectV2"]
    if not project:
        print(f"Project #{number} not found for user {owner}")
        return

    target_title = "[BACKEND] Write RSpec Test Suite for Subsidiary"
    target_id = None
    
    for node in project["items"]["nodes"]:
        content = node.get("content")
        if content and content.get("title") == target_title:
               target_id = node["id"]
               break
               
    if target_id:
        print(f"Moving {target_title} (ID: {target_id}) to 'To Do'...")
        mission_control.move_task_column(target_id, target_title, "To Do", env)
        print("Success.")
    else:
        print(f"Card '{target_title}' not found.")

if __name__ == "__main__":
    move_back_to_todo()
