// Check and save page path when page first loads in
// To assist "Back" button return to the previous page and 
// not stuck with previous query param of the same page
window.addEventListener('DOMContentLoaded', function() {
    const currentPath = window.location.pathname;
    const currentSearch = window.location.search;
    const previousPath = sessionStorage.getItem('previousPath');
    const previousSearch = sessionStorage.getItem('previousSearch');
    
    // If path changed (not query params) -> "real" navigation
    if (previousPath && previousPath !== currentPath) {
        sessionStorage.setItem('realPreviousPage', previousPath + previousSearch);
    }
    
    // Save current for next navigation
    sessionStorage.setItem('previousPath', currentPath);
    sessionStorage.setItem('previousSearch', currentSearch);
});

// To be called by pressing "back button"
// Returns to the previous page (endpoint), if not set, just return to previous record in history
// If no history, get endpoint from hardcoded mapping
function goBack() {
    const realPrevious = sessionStorage.getItem('realPreviousPage');
    
    if (realPrevious) {
        window.location.href = realPrevious;
    } else if (document.referrer && document.referrer.includes(window.location.host)) {
        history.back();
    } else {
        window.location.href = getParentPage();
    }
}

// The "current_page": "return_page" mapping
function getParentPage() {
    const urlPrefix = document.documentElement.getAttribute('data-url-prefix');
    const path = window.location.pathname;
    
    if (path.startsWith(urlPrefix + '/view/book/')) return urlPrefix + '/view/word';
    if (path.startsWith(urlPrefix + '/view/word/')) return urlPrefix + '/view/book';
    if (path.startsWith(urlPrefix + '/view/book')) return urlPrefix + '/view';
    if (path.startsWith(urlPrefix + '/view/word')) return urlPrefix + '/view';
    if (path.startsWith(urlPrefix + '/view/')) return urlPrefix + '/view';
    if (path.startsWith(urlPrefix + '/quiz/')) return urlPrefix + '/quiz';
    
    return '/';
}