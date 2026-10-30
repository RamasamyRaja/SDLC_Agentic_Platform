export const deleteInvestigation = (id) => {
    return api.delete(`/investigations/${id}`);
};
