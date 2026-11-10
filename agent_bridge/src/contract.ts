import { z } from 'zod';

export const Id = z.string().regex(/^[A-Za-z0-9_-]{1,64}$/);
// Supplied by the trusted local host, never by a model tool or MCP metadata.
export const Binding = z.object({
  ownerId: Id, hostId: Id, sessionId: Id, conversationId: Id, recipientId: Id,
  expiresAt: z.number().int().positive().safe(),
}).strict();
export type Binding = z.infer<typeof Binding>;
const Text = (max: number) => z.string().min(1).max(max)
  .refine(s => s.isWellFormed() && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(s));
export const DraftInput = z.object({
  requestId: Id, title: Text(160), instruction: Text(4000),
}).strict();
export type DraftInput = z.infer<typeof DraftInput>;
export const StatusInput = z.object({ draftId: Id }).strict();
export const Status = z.object({
  draftId: Id,
  state: z.literal('awaiting_owner_review'),
  ownerConsent: z.literal('not_requested'),
  transportReceipt: z.literal('none'),
  execution: z.literal('not_started'),
}).strict();
export type Status = z.infer<typeof Status>;
export const ErrorResult = z.object({ error: z.enum([
  'invalid_input', 'unavailable', 'conflict', 'limit_reached', 'internal_error',
]) }).strict();
export type ErrorCode = z.infer<typeof ErrorResult>['error'];
export class BoundaryError extends Error {
  code: ErrorCode;
  constructor(code: ErrorCode) { super(code); this.code = code; }
}
export const toolNames = ['create_task_draft', 'task_draft_status'] as const;
export const tools = [
  { name: toolNames[0], description: 'Save an inert task draft for later owner review. Never sends, approves or executes it.',
    inputSchema: z.toJSONSchema(DraftInput), outputSchema: z.toJSONSchema(Status),
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false } },
  { name: toolNames[1], description: 'Read only the status of a known draft in this exact host session and conversation.',
    inputSchema: z.toJSONSchema(StatusInput), outputSchema: z.toJSONSchema(Status),
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false } },
];
