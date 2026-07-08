const readyEventName = "skill-manage:web-ready";

window.dispatchEvent(new CustomEvent(readyEventName));

export { readyEventName };
