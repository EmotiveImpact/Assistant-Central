// Disposable acceptance fixture. This is not an owner-enrolment or product API.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Agent, Runner, MCPServerStdio, setTracingDisabled } from '@openai/agents';
import { DraftStore } from '../src/store.ts';
setTracingDisabled(true);
const input=JSON.parse(readFileSync(0,'utf8'));
const store=new DraftStore(input.launch.storePath,Buffer.from(input.launch.keyHex,'hex'));
let mcp;
try {
 if(input.operation==='revoke') {store.revoke(input.launch.binding);process.stdout.write('{"revoked":true}');}
 else {
  store.provision(input.launch.binding);
  const server=fileURLToPath(new URL('../src/stdio.ts',import.meta.url));
  const network=fileURLToPath(new URL('./no-network.mjs',import.meta.url));
  mcp=new MCPServerStdio({name:'Fictional owner review host',command:process.execPath,args:[server],env:{AC_BRIDGE_LAUNCH:JSON.stringify(input.launch),NODE_NO_WARNINGS:'1',NODE_OPTIONS:`--import=${network}`,HOME:input.home},cacheToolsList:false});
  await mcp.connect();let calls=0;
  const model={async getResponse(request){
    if(++calls===1){if(request.tools.length!==2)throw Error('unexpected tools');
      return {usage:{},output:[{type:'function_call',id:'fixture_call',callId:'fixture_call',name:'create_task_draft',arguments:JSON.stringify(input.draft),status:'completed'}]};}
    return {usage:{},output:[{type:'message',role:'assistant',status:'completed',content:[{type:'output_text',text:'Inert draft saved.'}]}]};
  },async *getStreamedResponse(){throw Error('unused');}};
  await new Runner({tracingDisabled:true}).run(new Agent({name:'Fictional host',model,instructions:'Save only the supplied inert fixture.',mcpServers:[mcp]}),'Prepare the fictional draft.',{maxTurns:3});
  if(calls!==2)throw Error('runner not exercised');
  const saved=store.dispatch(input.launch.binding,'create_task_draft',input.draft);
  process.stdout.write(JSON.stringify({draftId:saved.draftId,officialRunner:true,mcp:true}));
 }
}finally{await mcp?.close();store.close();}
