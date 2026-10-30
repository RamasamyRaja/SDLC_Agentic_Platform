import java.util.List;

class InvestigationService {
    public void deleteInvestigation(String id) {
        repository.delete(id);
    }
}
