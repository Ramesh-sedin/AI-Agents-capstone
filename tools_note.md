# Tool description note

I rewrote `get_ticket` from a generic description such as “Get a ticket” to “Get one support ticket and its customer by positive numeric ticket_id. Use this for the complete details of a specific open or resolved ticket.”

The original wording did not explain whether ticket ID was required or how much data would be returned. The rewritten description tells the model to use the tool for a specific ticket, require a positive numeric ID, and include the associated customer. It also makes the model less likely to use it for searching or to invent an ID when one is missing.
