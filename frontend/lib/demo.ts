import type { Impact } from "./api";
// Fixed illustrative snapshot. Never used as fallback for a live API response.
export const demoImpact: Impact = {
  status: "ASSESSED",
  assessed_at: "2026-10-18T08:00:00Z",
  sku: "FAN-MOTOR-45W",
  plant_code: "LK-HOM-PLANT",
  plant_name: "Homagama Assembly Plant",
  issues: [],
  allocations: [
    {
      demand_id: "demo-1",
      source_ref: "DEMAND-LK-001",
      required_at: "2026-10-18T12:30:00Z",
      remaining_demand: "500",
      stock_allocated_qty: "120",
      inbound_allocated_qty: "300",
      shortage_qty: "80",
      inbound_allocations: [],
    },
    {
      demand_id: "demo-2",
      source_ref: "DEMAND-LK-002",
      required_at: "2026-10-18T13:30:00Z",
      remaining_demand: "200",
      stock_allocated_qty: "0",
      inbound_allocated_qty: "0",
      shortage_qty: "200",
      inbound_allocations: [],
    },
  ],
  assumptions: [
    "Active shipment quantities are unreceived and unallocated.",
    "Inbound is usable at its current ETA.",
    "Reserved stock is excluded.",
    "Planning allocations are not persisted.",
  ],
};
