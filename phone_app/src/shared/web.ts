// One source of truth. These are the desktop app's own pure modules, read straight from the
// repository, so the phone says exactly what the desktop says about the same saved state.
// None of them touch the page: the parts that draw HTML stay in the browser. They are plain
// JavaScript, so the signatures they are used through are written out here.
/* eslint-disable @typescript-eslint/no-explicit-any */
import * as queue from '../../../workspace_ui/queue.mjs';
import * as home from '../../../workspace_ui/home.mjs';
import * as decide from '../../../workspace_ui/decide.mjs';
import * as team from '../../../workspace_ui/team.mjs';
import * as invites from '../../../workspace_ui/invites.mjs';
import * as phone from '../../../workspace_ui/phone.mjs';
import * as qr from '../../../workspace_ui/qr.mjs';
import * as bots from '../../../workspace_ui/bots.mjs';
import * as missions from '../../../workspace_ui/missions.mjs';
import * as model from '../../../pilot/web/model.mjs';

type Fn<A extends unknown[] = any[], R = any> = (...args: A) => R;
const m = <T>(value: unknown) => value as T;

export const homeQueue = m<Fn<[{ proposals?: unknown[]; approvals?: unknown; hostDrafts?: unknown; conversations?: unknown; joiners?: unknown[] }], unknown[]>>(queue.homeQueue);
export const uncheckedParts = m<Fn<[{ approvals?: unknown; hostDrafts?: unknown }], string[]>>(queue.uncheckedParts);
export const CARD = m<Record<string, { lead: string; action: string }>>(queue.CARD);
export const askerOf = m<Fn<[unknown, { me?: string; mine?: string; peer?: unknown }], { owner: string; agent: string; yours: boolean }>>(queue.askerOf);
export const moreLine = m<Fn<[number], string>>(queue.moreLine);
export const closingLine = m<Fn<[string[]?], string>>(queue.closingLine);

export const homeGreeting = m<Fn<[number], string>>(home.homeGreeting);
export const isEvening = m<Fn<[number], boolean>>(home.isEvening);
export const budgetSummary = m<Fn<[unknown[], unknown[]], unknown[]>>(home.budgetSummary);
export const doneToday = m<Fn<[unknown[], number?], unknown[]>>(home.doneToday);
export const doneLine = m<Fn<[unknown, unknown], string>>(home.doneLine);
export const eveningSummary = m<Fn<[unknown[], Fn], string>>(home.eveningSummary);
export const shortKey = m<Fn<[string], string>>(home.shortKey);

export const decisionQuestion = m<Fn<[unknown, { agent?: string; owner?: string }], string>>(decide.decisionQuestion);
export const decisionRows = m<Fn<[unknown, { agent?: string; owner?: string; actions?: string[] }], [string, string][]>>(decide.decisionRows);
export const needsHold = m<Fn<[unknown, string], boolean>>(decide.needsHold);

export const STEPS = m<readonly string[]>(team.STEPS);
export const teamsOf = m<Fn<[unknown], any[]>>(team.teamsOf);
export const partOf = m<Fn<[unknown, unknown], any>>(team.partOf);
export const partLead = m<Fn<[unknown], string>>(team.partLead);
export const teamCounts = m<Fn<[unknown], Record<string, number>>>(team.teamCounts);
export const teamLine = m<Fn<[unknown], string>>(team.teamLine);
export const stepShare = m<Fn<[string], number>>(team.stepShare);

export const inviteFromText = m<Fn<[unknown], string>>(invites.inviteFromText);
export const relayEnabled = m<Fn<[unknown], boolean>>(invites.relayEnabled);
export const validateRelay = m<Fn<[unknown], unknown>>(invites.validateRelay);
export const expiresIn = m<Fn<[number, number?], string>>(invites.expiresIn);
export const joinProblem = m<Fn<[string, string?], string>>(invites.joinProblem);
export const joinerCards = m<Fn<[unknown], unknown[]>>(invites.joinerCards);

export const ANSWER_LIMIT = m<string>(phone.ANSWER_LIMIT);

export const qrMatrix = m<Fn<[string, { mask?: number }?], { version: number; mask: number; size: number; modules: boolean[][] }>>(qr.qrMatrix);
export const qrPath = m<Fn<[{ size: number; modules: boolean[][] }], { path: string; size: number }>>(qr.qrPath);

export const SHAPES = m<Record<'pebble' | 'bean' | 'cloud' | 'hex' | 'drop' | 'squircle', string>>(bots.SHAPES);
export const COLOURS = m<Record<string, string>>(bots.COLOURS);
export const botTraits = m<Fn<[string], { shape: keyof typeof SHAPES; colour: string; body: string }>>(bots.botTraits);

export const exactMoney = m<Fn<[number, string?], string>>(missions.exactMoney);
export const money = m<Fn<[number, string?], string>>(missions.money);

export const validateState = m<Fn<[unknown], unknown>>(model.validateState);
export const validateReview = m<Fn<[unknown, unknown], unknown>>(model.validateReview);
export const stateLabel = m<Fn<[string], string>>(model.stateLabel);

const isPending = m<Fn<[unknown], boolean>>(model.isPending);
const statusClass = m<Fn<[string], string>>(model.statusClass);

// The same rule as attentionItems in workspace_ui/projections.mjs (newest first). That module
// imports model.mjs by the path the desktop server serves it on, so it is restated here.
export function attentionItems(state: { items: { direction: string; state: string }[] }) {
  return state.items.slice().reverse().filter(item =>
    (item.direction === 'incoming' && isPending(item)) || item.state === 'uncertain' || statusClass(item.state) === 'unknown');
}
