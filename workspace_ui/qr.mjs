// A small QR code maker for invite links. Pure, so the page and the tests agree.
// Byte mode, error correction level L, versions 1 to 40 (ISO/IEC 18004). It draws nothing
// itself: `qrMatrix` returns the squares and `qrPath` turns them into one SVG path.

// Error correction codewords per block, and the number of blocks, at level L for each version.
const ECC_PER_BLOCK=[7,10,15,20,26,18,20,24,30,18,20,24,26,30,22,24,28,30,28,28,28,28,30,30,26,28,30,30,30,30,30,30,30,30,30,30,30,30,30,30];
const BLOCKS=[1,1,1,1,1,2,2,2,2,4,4,4,4,4,6,6,6,6,7,8,8,9,9,10,12,12,12,13,14,15,16,17,18,19,19,20,21,22,24,25];

function rawModules(version){
  let count=(16*version+128)*version+64;
  if(version>=2){const align=Math.floor(version/7)+2;count-=(25*align-10)*align-55;if(version>=7)count-=36;}
  return count;
}
// How many bytes of data fit in one version.
export function capacity(version){
  const codewords=Math.floor(rawModules(version)/8)-ECC_PER_BLOCK[version-1]*BLOCKS[version-1];
  // Four bits of mode and a length of one byte (versions 1 to 9) or two.
  return codewords-(version<10?2:3);
}

// Reed-Solomon over GF(256) with the QR polynomial x^8+x^4+x^3+x^2+1.
function multiply(x,y){let z=0;for(let i=7;i>=0;i--){z=(z<<1)^((z>>>7)*0x11D);z^=((y>>>i)&1)*x;}return z;}
function divisor(degree){
  const result=new Array(degree).fill(0);result[degree-1]=1;let root=1;
  for(let i=0;i<degree;i++){
    for(let j=0;j<degree;j++){result[j]=multiply(result[j],root);if(j+1<degree)result[j]^=result[j+1];}
    root=multiply(root,2);
  }
  return result;
}
function remainder(data,generator){
  const result=new Array(generator.length).fill(0);
  for(const byte of data){const factor=byte^result.shift();result.push(0);generator.forEach((coefficient,i)=>{result[i]^=multiply(coefficient,factor);});}
  return result;
}

function codewords(bytes,version){
  const total=Math.floor(rawModules(version)/8),blocks=BLOCKS[version-1],ecc=ECC_PER_BLOCK[version-1],dataLength=total-ecc*blocks;
  const bits=[],push=(value,length)=>{for(let i=length-1;i>=0;i--)bits.push((value>>>i)&1);};
  push(4,4);push(bytes.length,version<10?8:16);for(const byte of bytes)push(byte,8);
  push(0,Math.min(4,dataLength*8-bits.length));push(0,(8-bits.length%8)%8);
  for(let pad=0xEC;bits.length<dataLength*8;pad^=0xEC^0x11)push(pad,8);
  const data=[];for(let i=0;i<bits.length;i+=8)data.push(bits.slice(i,i+8).reduce((value,bit)=>(value<<1)|bit,0));
  // Split into blocks, add each block's error correction, then interleave.
  const short=blocks-total%blocks,shortLength=Math.floor(total/blocks),generator=divisor(ecc),parts=[];
  for(let i=0,at=0;i<blocks;i++){
    const length=shortLength-ecc+(i<short?0:1),block=data.slice(at,at+length);at+=length;
    const check=remainder(block,generator);if(i<short)block.push(0);parts.push(block.concat(check));
  }
  const result=[];
  for(let i=0;i<parts[0].length;i++)parts.forEach((block,j)=>{if(i!==shortLength-ecc||j>=short)result.push(block[i]);});
  return result;
}

function alignmentCentres(version,size){
  if(version===1)return [];
  const count=Math.floor(version/7)+2,step=version===32?26:Math.floor((version*4+count*2+1)/(count*2-2))*2,result=[6];
  for(let position=size-7;result.length<count;position-=step)result.splice(1,0,position);
  return result;
}

function build(version,data,mask){
  const size=version*4+17,modules=Array.from({length:size},()=>new Array(size).fill(false)),fixed=Array.from({length:size},()=>new Array(size).fill(false));
  const set=(x,y,dark)=>{modules[y][x]=dark;fixed[y][x]=true;};
  for(let i=0;i<size;i++){set(6,i,i%2===0);set(i,6,i%2===0);}
  const finder=(cx,cy)=>{for(let dy=-4;dy<=4;dy++)for(let dx=-4;dx<=4;dx++){const distance=Math.max(Math.abs(dx),Math.abs(dy)),x=cx+dx,y=cy+dy;if(x>=0&&x<size&&y>=0&&y<size)set(x,y,distance!==2&&distance!==4);}};
  finder(3,3);finder(size-4,3);finder(3,size-4);
  const centres=alignmentCentres(version,size),last=centres.length-1;
  centres.forEach((cx,i)=>centres.forEach((cy,j)=>{
    if((i===0&&j===0)||(i===0&&j===last)||(i===last&&j===0))return;
    for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++)set(cx+dx,cy+dy,Math.max(Math.abs(dx),Math.abs(dy))!==1);
  }));
  const format=()=>{
    const value=(1<<3)|mask;let rest=value;for(let i=0;i<10;i++)rest=(rest<<1)^((rest>>>9)*0x537);
    const bits=((value<<10)|rest)^0x5412,bit=i=>((bits>>>i)&1)!==0;
    for(let i=0;i<=5;i++)set(8,i,bit(i));
    set(8,7,bit(6));set(8,8,bit(7));set(7,8,bit(8));
    for(let i=9;i<15;i++)set(14-i,8,bit(i));
    for(let i=0;i<8;i++)set(size-1-i,8,bit(i));
    for(let i=8;i<15;i++)set(8,size-15+i,bit(i));
    set(8,size-8,true);
  };
  format();
  if(version>=7){
    let rest=version;for(let i=0;i<12;i++)rest=(rest<<1)^((rest>>>11)*0x1F25);
    const bits=(version<<12)|rest;
    for(let i=0;i<18;i++){const dark=((bits>>>i)&1)!==0,a=size-11+i%3,b=Math.floor(i/3);set(a,b,dark);set(b,a,dark);}
  }
  // Lay the data in the zigzag, two columns at a time from the right, skipping the timing column.
  let index=0;
  for(let right=size-1;right>=1;right-=2){
    if(right===6)right=5;
    for(let step=0;step<size;step++)for(let j=0;j<2;j++){
      const x=right-j,upward=((right+1)&2)===0,y=upward?size-1-step:step;
      if(!fixed[y][x]&&index<data.length*8){modules[y][x]=((data[index>>>3]>>>(7-(index&7)))&1)!==0;index++;}
    }
  }
  const flips=[(x,y)=>(x+y)%2===0,(x,y)=>y%2===0,(x,y)=>x%3===0,(x,y)=>(x+y)%3===0,(x,y)=>(Math.floor(x/3)+Math.floor(y/2))%2===0,
    (x,y)=>x*y%2+x*y%3===0,(x,y)=>(x*y%2+x*y%3)%2===0,(x,y)=>((x+y)%2+x*y%3)%2===0][mask];
  for(let y=0;y<size;y++)for(let x=0;x<size;x++)if(!fixed[y][x]&&flips(x,y))modules[y][x]=!modules[y][x];
  return modules;
}

// The standard penalty score: lower reads more easily.
function penalty(modules){
  const size=modules.length;let score=0,dark=0;
  const line=cells=>{
    let run=1;
    for(let i=1;i<=size;i++){if(i<size&&cells[i]===cells[i-1])run++;else{if(run>=5)score+=run-2;run=1;}}
    for(let i=0;i+10<size;i++){
      const a=cells.slice(i,i+11);
      if([true,false,true,true,true,false,true,false,false,false,false].every((v,k)=>a[k]===v)||[false,false,false,false,true,false,true,true,true,false,true].every((v,k)=>a[k]===v))score+=40;
    }
  };
  for(let y=0;y<size;y++){line(modules[y]);for(const cell of modules[y])if(cell)dark++;}
  for(let x=0;x<size;x++)line(modules.map(row=>row[x]));
  for(let y=0;y+1<size;y++)for(let x=0;x+1<size;x++){const c=modules[y][x];if(c===modules[y][x+1]&&c===modules[y+1][x]&&c===modules[y+1][x+1])score+=3;}
  score+=Math.floor(Math.abs(dark*20-size*size*10)/(size*size))*10;
  return score;
}

// The squares for a piece of text: `modules[y][x]` is true where a square is dark.
export function qrMatrix(text,{mask}={}){
  const bytes=[...new TextEncoder().encode(String(text))];
  let version=1;while(version<=40&&capacity(version)<bytes.length)version++;
  if(version>40)throw new Error('Too long for a QR code.');
  const data=codewords(bytes,version);
  if(Number.isInteger(mask)&&mask>=0&&mask<=7)return {version,mask,size:version*4+17,modules:build(version,data,mask)};
  let best=null;
  for(let candidate=0;candidate<8;candidate++){
    const modules=build(version,data,candidate),score=penalty(modules);
    if(!best||score<best.score)best={version,mask:candidate,size:version*4+17,modules,score};
  }
  delete best.score;
  return best;
}

// One SVG path for the dark squares, with the four quiet squares the standard asks for all round.
export const QUIET=4;
export function qrPath(matrix){
  let path='';
  matrix.modules.forEach((row,y)=>{
    for(let x=0;x<row.length;x++){
      if(!row[x])continue;
      let end=x;while(end+1<row.length&&row[end+1])end++;
      path+=`M${x+QUIET},${y+QUIET}h${end-x+1}v1h-${end-x+1}z`;x=end;
    }
  });
  return {path,size:matrix.size+QUIET*2};
}
