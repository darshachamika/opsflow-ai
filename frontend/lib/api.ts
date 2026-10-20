export type Allocation = {
  demand_id: string;
  source_ref: string;
  required_at: string;
  remaining_demand: string;
  stock_allocated_qty: string;
  inbound_allocated_qty: string;
  shortage_qty: string;
  inbound_allocations: { shipment_line_id: string; quantity: string }[];
};
export type Impact = {
  status: string;
  assessed_at: string;
  sku: string;
  plant_code: string;
  plant_name: string;
  issues: { code: string; reference: string; message: string }[];
  allocations: Allocation[];
  assumptions: string[];
};
export type Actor = { subject: string; role: string };
const base = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");
export async function api<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${base}/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    if (response.status === 401)
      throw new Error(
        "Your token is missing or expired. Reconnect with a valid application token.",
      );
    if (response.status === 403)
      throw new Error("Your role does not have access to this action.");
    if (response.status === 404)
      throw new Error(
        "No matching record was found. Check the product, plant or incident ID.",
      );
    throw new Error(
      `API request failed (${response.status}). Check backend availability and configuration.`,
    );
  }
  return response.json() as Promise<T>;
}
export const formatQty = (value: number | string) =>
  new Intl.NumberFormat("en-LK", { maximumFractionDigits: 3 }).format(
    Number(value),
  );
