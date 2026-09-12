export function renderPage(content, style) { return `<!doctype html><html><head><style>${style.css}</style></head><body><h1>${content.title}</h1><main>${content.body}</main></body></html>`; }
