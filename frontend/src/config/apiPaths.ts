/** Exact collection routes registered by FastAPI. Their trailing slash is part
 * of the contract: avoiding a framework redirect preserves reverse-proxy prefixes. */
export const API_COLLECTION_PATHS = {
  AGENTS: '/agents/',
  NOTIFICATIONS: '/notifications/',
  DEVICES: '/devices/',
} as const;
