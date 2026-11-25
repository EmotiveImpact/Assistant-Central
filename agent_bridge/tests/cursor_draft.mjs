// A no-model official SDK host for the owner-to-owner acceptance fixture.
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { serve } from '@grok/agent-sdk';

export async function prepareCursorDraft(input) {
  const project = await mkdtemp(join(input.home, 'cursor-mission-'));
  const sdk = JSON.stringify(import.meta.resolve('@grok/agent-sdk'));
  const stdio = fileURLToPath(new URL('../src/stdio.ts', import.meta.url));
  const blockedNetwork = fileURLToPath(new URL('./no-network.mjs', import.meta.url));
  let handle;
  try {
    await mkdir(join(project, 'bot', 'mcp-connections'), {recursive:true});
    await writeFile(join(project, 'package.json'), '{"type":"module"}');
    await writeFile(join(project, 'bot', 'instructions.md'), 'Prepare an inert owner draft.');
    await writeFile(join(project, 'bot', 'agent.ts'),
      'import {defineAgent,emptyFs} from '+sdk+';export default defineAgent({name:"Mission fixture",tools:[],skills:false,fs:emptyFs()});');
    // Launch secrets stay in the disposable process environment, outside the module.
    process.env.AC_BRIDGE_LAUNCH = JSON.stringify(input.launch);
    await writeFile(join(project,'bot','mcp-connections','central.ts'),
      'import {defineConnection} from '+sdk+';export default defineConnection({command:process.execPath,args:['+
      JSON.stringify(stdio)+'],env:{AC_BRIDGE_LAUNCH:process.env.AC_BRIDGE_LAUNCH,NODE_OPTIONS:'+
      JSON.stringify('--import='+blockedNetwork)+'},advertiseTools:true,tools:["create_task_draft","task_draft_status"]});');
    handle = await serve(project,{host:'127.0.0.1',port:0,stateRoot:join(project,'state'),
      schedules:false,reminders:false,playground:false,docs:false,mode:'single',logger(){}});
    const result = await handle.callTool('create_task_draft',input.draft);
    if(result.isError || !JSON.stringify(result.result).includes('awaiting_owner_review'))
      throw new Error('The SDK host did not retain the draft');
  } finally {
    await handle?.close();
    delete process.env.AC_BRIDGE_LAUNCH;
    await rm(project,{recursive:true,force:true});
  }
}
