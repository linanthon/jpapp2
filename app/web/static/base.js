// Check and save page path when page first loads in
// To assist "Back" button return to the previous page and 
// not stuck with previous query param of the same page
// window.addEventListener('DOMContentLoaded', function() {
//     const currentPath = window.location.pathname;
//     const currentSearch = window.location.search;
//     const previousPath = sessionStorage.getItem('previousPath');
//     const previousSearch = sessionStorage.getItem('previousSearch');
    
//     // If path changed (not query params) -> "real" navigation
//     if (previousPath && previousPath !== currentPath && previousPath.length < currentPath.length) {
//         sessionStorage.setItem('realPreviousPage', previousPath + previousSearch);
//     }
    
//     // Save current for next navigation
//     sessionStorage.setItem('previousPath', currentPath);
//     sessionStorage.setItem('previousSearch', currentSearch);
// });

// To be called by pressing "back button"
// Return to the previous page from hardcoded mapping
// function goBack() {
    // const realPrevious = sessionStorage.getItem('realPreviousPage');
    
    // if (realPrevious) {
    //     // Remove `realPreviousPage` if going back this way, if in need of go back after this
    //     // it'll just use the history.back()
    //     sessionStorage.removeItem('realPreviousPage');
    //     window.location.href = realPrevious;
    // } else if (document.referrer && document.referrer.includes(window.location.host)) {
    //     history.back();
    // } else {
    // window.location.href = getParentPage();
    // }
// }

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
    window.location.href = getParentPage();
}

// The "current_page": "return_page" mapping
function getParentPage() {
    const urlPrefix = document.documentElement.getAttribute('data-url-prefix');
    const path = window.location.pathname;
    
    if (path.startsWith(urlPrefix + '/view/book/')) return urlPrefix + '/view/book';

    if (path.startsWith(urlPrefix + '/view/word/')) {
        const savePreviousPage = sessionStorage.getItem('savePreviousPage');
        if (savePreviousPage && (savePreviousPage.startsWith(urlPrefix + '/view/search-word') || savePreviousPage.startsWith(urlPrefix + '/view/word?'))) {
            return savePreviousPage;
        }
        return urlPrefix + '/view/word';
    }

    if (path.startsWith(urlPrefix + '/view/')) return urlPrefix + '/view';
    
    return urlPrefix + '';
}