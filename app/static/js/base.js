// Save the previous page url and params, note that this will run when exiting the page
// So the previous value will get updated into the current page before the back button worked
// -> we need to save the previous of previous to work correctly
window.addEventListener('DOMContentLoaded', function() {
    const currentPath = window.location.pathname;
    const currentSearch = window.location.search;
    const previousPath = sessionStorage.getItem('previousPath');
    const previousSearch = sessionStorage.getItem('previousSearch');
    const isReloading = sessionStorage.getItem('isNavigatingBack') === 'true';
    
    if (previousPath && !isReloading) {
        let prevPath = previousPath
        if (previousSearch) {
            prevPath += previousSearch
        }
        sessionStorage.setItem('savePreviousPage', prevPath);
    } else if (isReloading) {
        sessionStorage.setItem('savePreviousPage', '');
    }

    // NOW update with current page
    sessionStorage.setItem('isNavigatingBack', 'false');
    sessionStorage.setItem('previousPath', currentPath);
    sessionStorage.setItem('previousSearch', currentSearch);
});

function goBack() {
    sessionStorage.setItem('isNavigatingBack', 'true');
    navigateWithAuth(getParentPage());
}

// The "current_page": "return_page" mapping
function getParentPage() {
    const urlPrefix = document.documentElement.getAttribute('data-url-prefix');
    const path = window.location.pathname;
    
    if (path.startsWith(urlPrefix + '/view/book/')) return urlPrefix + '/view/book';

    if (path.startsWith(urlPrefix + '/view/word/')) {
        const savePreviousPage = sessionStorage.getItem('savePreviousPage');
        if (savePreviousPage && (savePreviousPage.startsWith(urlPrefix + '/view/search-word') || 
            savePreviousPage.startsWith(urlPrefix + '/view/word?') || savePreviousPage.startsWith(urlPrefix + '/quiz/jp'))) {
            return savePreviousPage;
        }
        return urlPrefix + '/view/word';
    }

    if (path.startsWith(urlPrefix + '/view/')) return urlPrefix + '/view';
    
    if (path.startsWith(urlPrefix + '/quiz/')) return urlPrefix + '/quiz';
    
    return urlPrefix;
}

function goHome() {
    window.location.href = document.documentElement.getAttribute('data-url-prefix');
}