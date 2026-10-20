import type { CSSProperties } from "react";
import { Box, Truck, TriangleAlert } from "lucide-react";
export default function SupplyChart({ demand, stock, inbound, shortage }: { demand: number; stock: number; inbound: number; shortage: number }) {
 const percent = (n:number) => demand > 0 ? Math.max(0,Math.min(100,n/demand*100)) : 0;
 const a=percent(stock),b=Math.min(100,a+percent(inbound));
 const rows=[{name:"Available stock allocated",value:stock,color:"#12b89b",Icon:Box},{name:"Inbound arriving on time",value:inbound,color:"#7663f4",Icon:Truck},{name:"Still to recover",value:shortage,color:"#f4a24d",Icon:TriangleAlert}];
 return <section className="supply-visual" aria-label="Supply coverage breakdown">
  <div className="coverage-ring" role="img" aria-label={`${stock} stock, ${inbound} inbound, ${shortage} shortage of ${demand} units`} style={{"--ring": demand ? `conic-gradient(#12b89b 0% ${a}%,#7663f4 ${a}% ${b}%,#f4a24d ${b}% 100%)` : "#e9edf5"} as CSSProperties}><div><strong>{demand ? Math.round(percent(stock+inbound)) : "—"}{demand > 0 && <small>%</small>}</strong><span>Demand covered</span></div></div>
  <div className="supply-bars"><div className="supply-chart-title"><h3>Supply coverage</h3><span>{demand.toLocaleString()} units needed</span></div>{rows.map(({name,value,color,Icon})=><div className="supply-bar-row" key={name}><div><span><Icon size={15}/>{name}</span><strong>{value.toLocaleString()}</strong></div><div className="supply-track"><span style={{width:`${percent(value)}%`,background:color}}/></div></div>)}<p>Current assessment · stock and on-time inbound only</p></div>
 </section>;
}
