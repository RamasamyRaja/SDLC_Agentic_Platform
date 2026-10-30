import { api } from "./api";

export function deleteInvestigation(id: string) {
    return api.delete(`/investigations/${id}`);
}
