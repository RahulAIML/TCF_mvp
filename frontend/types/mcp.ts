export interface McpTool {
  name: string;
  title: string;
  description: string;
}

export interface McpInfo {
  mcp_url: string;
  transport: string;
  languages: { code: string; locale: string; name: string; voices: number }[];
  tools: McpTool[];
  max_active_tokens: number;
}

export interface McpTokenRecord {
  id: string;
  name: string;
  hint: string;
  created_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface McpCreatedToken {
  /** The full token. Returned once, when it is created; the server keeps only its hash. */
  token: string;
  record: McpTokenRecord;
}
