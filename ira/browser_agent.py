"""Autonomous Browser Agent — operates in the Chrome CDP browser session using visual overlays and structured JSON planning."""
from __future__ import annotations
import os
import time
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import Optional, Literal

from key_manager import APIKeyManager
from ui import print_tool_call, print_tool_result

# JS to inject overlays
MARKER_SCRIPT = """
(() => {
    // Remove any existing IRA overlays/attributes first
    document.querySelectorAll('.ira-element-overlay').forEach(el => el.remove());
    document.querySelectorAll('[data-ira-index]').forEach(el => el.removeAttribute('data-ira-index'));

    // Select all potential interactive elements
    const elements = Array.from(document.querySelectorAll(
        'button, a, input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="menuitem"], [onclick]'
    ));

    // Also find elements that have cursor: pointer
    const allElements = document.querySelectorAll('*');
    for (const el of allElements) {
        if (elements.includes(el)) continue;
        const style = window.getComputedStyle(el);
        if (style.cursor === 'pointer') {
            elements.push(el);
        }
    }

    let index = 1;
    const mapping = {};

    elements.forEach(el => {
        // Visibility checks
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        
        // Check if element is offscreen
        if (rect.bottom < 0 || rect.top > window.innerHeight || rect.right < 0 || rect.left > window.innerWidth) {
            return;
        }

        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
            return;
        }

        // Set custom attribute for Playwright click/type reference
        el.setAttribute('data-ira-index', index);

        // Draw overlay label
        const overlay = document.createElement('div');
        overlay.className = 'ira-element-overlay';
        overlay.style.position = 'fixed';
        overlay.style.left = `${rect.left}px`;
        overlay.style.top = `${rect.top}px`;
        overlay.style.width = `${rect.width}px`;
        overlay.style.height = `${rect.height}px`;
        overlay.style.border = '1px solid rgba(255, 40, 40, 0.85)';
        overlay.style.boxSizing = 'border-box';
        overlay.style.pointerEvents = 'none';
        overlay.style.zIndex = '2147483647'; // Maximum z-index
        overlay.style.backgroundColor = 'rgba(255, 40, 40, 0.05)';

        // Number Badge
        const badge = document.createElement('div');
        badge.innerText = index;
        badge.style.position = 'absolute';
        badge.style.left = '0px';
        badge.style.top = '-15px';
        if (rect.top < 15) {
            badge.style.top = '0px'; // inside if too high
        }
        badge.style.backgroundColor = 'rgb(220, 30, 30)';
        badge.style.color = '#fff';
        badge.style.fontSize = '10px';
        badge.style.fontWeight = 'bold';
        badge.style.padding = '1px 3px';
        badge.style.borderRadius = '2px';
        badge.style.lineHeight = '1';
        badge.style.whiteSpace = 'nowrap';
        badge.style.zIndex = '2147483647';

        overlay.appendChild(badge);
        document.body.appendChild(overlay);

        mapping[index] = {
            tagName: el.tagName.toLowerCase(),
            text: el.innerText ? el.innerText.trim().substring(0, 50) : '',
            placeholder: el.placeholder || '',
            role: el.getAttribute('role') || ''
        };
        index++;
    });

    return { count: index - 1, mapping: mapping };
})()
"""

class BrowserAction(BaseModel):
    thought: str = Field(description="Analyze the page state visual markings and plan the next action.")
    action: Literal["click", "type", "scroll", "navigate", "go_back", "wait", "finish"] = Field(description="The action to perform.")
    element_index: Optional[int] = Field(None, description="The index number of the element to interact with (required for click and type).")
    text: Optional[str] = Field(None, description="The text to type (for 'type') or the URL to navigate to (for 'navigate').")
    direction: Optional[Literal["up", "down"]] = Field("down", description="Scroll direction (for 'scroll').")
    answer: Optional[str] = Field(None, description="The final answer or summary of the task (required for 'finish').")


def run_browser_agent(task: str, event_callback=None) -> str:
    """Connect to the browser, run an autonomous agent using Playwright, and complete the web-based task."""
    from tools import run_in_browser_thread, get_browser_page
    
    def _run_agent_inner():
        # Get/open the browser page
        page = get_browser_page()
        if not page:
            return "Error: Could not connect to browser."
            
        km = APIKeyManager()
        
        # Initial status update
        if event_callback:
            event_callback("thought", {"text": f"Starting autonomous browser task: {task}"})
            
        for step in range(1, 16): # Max 15 steps
            # Check stop request
            from stop import is_stop_requested
            if is_stop_requested():
                return "Task stopped by user."
                
            # 1. Annotate active page and get screenshot + element mapping
            try:
                # If page is on about:blank, navigate to google first if task is a search
                if page.url == "about:blank" and not any(kw in task.lower() for kw in ["http", "www", "navigate"]):
                    page.goto("https://www.google.com", wait_until="domcontentloaded")
                    time.sleep(1.0)
                    
                # Run the marker script
                res = page.evaluate(MARKER_SCRIPT)
                mapping = res.get("mapping", {})
                count = res.get("count", 0)
                
                # Take screenshot
                import tempfile
                from pathlib import Path
                tmp_path = Path(tempfile.gettempdir()) / f"ira_browser_step_{step}.png"
                page.screenshot(path=str(tmp_path), full_page=False)
                
                # Cleanup overlays immediately
                page.evaluate("document.querySelectorAll('.ira-element-overlay').forEach(el => el.remove());")
                
                with open(tmp_path, "rb") as f:
                    img_bytes = f.read()
                    
                # Emit screenshot to user UI
                if event_callback:
                    event_callback("screenshot", {"path": str(tmp_path)})
                    
            except Exception as e:
                # If screenshot fails (e.g. browser loading), wait and retry
                print(f"[BrowserAgent] Marker/screenshot failed: {e}. Retrying in 1.5s...")
                time.sleep(1.5)
                continue
                
            # 2. Build contents for Gemini
            prompt_text = (
                f"Task: {task}\n"
                f"Step: {step}/15\n\n"
                f"Page Title: {page.title()}\n"
                f"Page URL: {page.url}\n\n"
                f"Interactive elements are highlighted with red boxes and number tags on the screenshot. "
                f"You MUST use the number tags on the screenshot to click or type. "
                f"If you need to enter text, select the element tag, type the text, and press enter. "
                f"If the element you want isn't visible, use scroll down/up. "
                f"Choose the next action and return it using the specified JSON schema."
            )
            
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt_text),
                        types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    ]
                )
            ]
            
            # 3. Call Gemini
            model = "gemini-3.5-flash"  # or fallback if needed
            success = False
            response = None
            errors = []
            
            for attempt in range(len(km.keys)):
                key = km.get_key()
                if not key:
                    continue
                client = genai.Client(api_key=key)
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=BrowserAction,
                            temperature=0.1,
                            system_instruction="You are an autonomous browser automation agent. Your goal is to complete the user's web task by visually analyzing the screenshot with red number overlays and choosing the next action."
                        )
                    )
                    success = True
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "quota" in err_str.lower():
                        km.mark_rate_limited(key)
                        errors.append(f"429: {key[-6:]}")
                    else:
                        errors.append(str(e))
                        
            if not success:
                return f"Error: Failed to call Gemini API. Errors: {errors}"
                
            # 4. Parse action
            try:
                action_data = json.loads(response.text)
                action_obj = BrowserAction(**action_data)
            except Exception as e:
                return f"Error parsing model response: {e}. Raw: {response.text}"
                
            # 5. Display thoughts and emit
            thought = action_obj.thought
            action = action_obj.action
            element_index = action_obj.element_index
            text = action_obj.text
            direction = action_obj.direction
            answer = action_obj.answer
            
            print_tool_call(f"BrowserAgent Step {step}", f"Action: {action}, Element: {element_index}, Text: {text}")
            if event_callback:
                event_callback("thought", {"text": f"Step {step}: {thought}"})
                event_callback("tool_call", {
                    "name": f"Browser:{action}",
                    "args": {"element": element_index, "text": text, "direction": direction, "url": text},
                    "args_text": f"element={element_index}, text={text}" if text else f"element={element_index}"
                })
                
            # 6. Execute action
            result_str = ""
            try:
                if action == "finish":
                    return answer or "Task completed."
                    
                elif action == "navigate":
                    if not text:
                        result_str = "Error: Navigate URL not provided."
                    else:
                        if not text.startswith("http"):
                            text = "https://" + text
                        page.goto(text, wait_until="domcontentloaded", timeout=15000)
                        result_str = f"Navigated to {text}"
                        
                elif action == "go_back":
                    page.go_back()
                    result_str = "Went back to previous page"
                    
                elif action == "wait":
                    time.sleep(3.0)
                    result_str = "Waited 3 seconds"
                    
                elif action == "scroll":
                    scroll_dir = direction or "down"
                    if scroll_dir == "up":
                        page.mouse.wheel(0, -600)
                    else:
                        page.mouse.wheel(0, 600)
                    result_str = f"Scrolled {scroll_dir}"
                    
                elif action in ("click", "type"):
                    if element_index is None:
                        result_str = f"Error: element_index not provided for {action} action."
                    else:
                        # Target using data-ira-index
                        selector = f"[data-ira-index='{element_index}']"
                        try:
                            # Scroll element into view first
                            page.locator(selector).scroll_into_view_if_needed(timeout=2000)
                            time.sleep(0.1)
                            
                            if action == "click":
                                page.click(selector, timeout=5000)
                                result_str = f"Clicked element [{element_index}]"
                            elif action == "type":
                                page.click(selector, timeout=2000) # focus
                                page.fill(selector, text or "", timeout=5000)
                                page.press(selector, "Enter")
                                result_str = f"Typed '{text}' into element [{element_index}] and pressed Enter"
                        except Exception as el_err:
                            result_str = f"Error performing {action} on element [{element_index}]: {el_err}"
                            
                else:
                    result_str = f"Unknown action: {action}"
                    
            except Exception as act_err:
                result_str = f"Error executing action: {act_err}"
                
            print_tool_result(result_str)
            if event_callback:
                event_callback("tool_result", {"name": f"Browser:{action}", "result": result_str})
                
            # Allow page to settle
            time.sleep(1.0)
            
        return "Task exceeded maximum steps (15) without finishing."

    try:
        return run_in_browser_thread(_run_agent_inner)
    except Exception as e:
        return f"Browser agent error: {e}"
