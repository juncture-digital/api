const junctureDomains = new Set(['juncture-digital.org', 'beta.juncture-digital.org', 'dev.juncture-digital.org', 'editor.juncture-digital.org', 'visual-essays.net', 'localhost:8080', 'localhost:5555'])
const isJuncture = junctureDomains.has(location.host)
let PREFIX = window.PREFIX
let REF = window.REF
// console.log(`PREFIX=${PREFIX} REF=${REF} host=${location.host} isJuncture=${isJuncture}`)

// Remove ref query argument from browser URL if same as REF
if (!isJuncture) {
  let re = new RegExp(`^\/${PREFIX}`)
  let browserPath = `${location.origin}${location.pathname.replace(re,'')}`
  let qargsRef = (new URL(document.location)).searchParams.get('ref')
  if (qargsRef && qargsRef !== REF) browserPath += `?ref=${qargsRef}`
  window.history.replaceState({}, document.title, browserPath)
}

window.isMobile = ('ontouchstart' in document.documentElement && /mobi/i.test(navigator.userAgent) )
window.isEditor = location.port === '5555' || location.hostname.indexOf('editor') == 0
// console.log(`main.js: isMobile=${window.isMobile} height=${window.innerHeight}`)

/*
function domPath(el) {
  var stack = []
  while ( el.parentNode != null ) {
    let sibCount = 0
    let sibIndex = 0
    for ( var i = 0; i < el.parentNode.childNodes.length; i++ ) {
      let sib = el.parentNode.childNodes[i];
      if ( sib.nodeName == el.nodeName ) {
        if ( sib === el ) {
          sibIndex = sibCount;
        }
        sibCount++
      }
    }
    if ( el.hasAttribute('id') && el.id != '' ) {
      stack.unshift(el.nodeName.toLowerCase() + `#${el.id}`)
    } else if ( sibCount > 1 ) {
      stack.unshift(el.nodeName.toLowerCase() + (sibIndex > 0 ? `[${sibIndex}]` : ''))
    } else {
      stack.unshift(el.nodeName.toLowerCase())
    }
    el = el.parentNode
  }
  return stack.join('.')
}

function findStickyElems() {
  let stickyElems = Array.from(document.querySelectorAll('.sticky'))
    // .filter(el => el.localName.toLowerCase() !== 've-content-selector')
  
  let stickyNavBarIdx = stickyElems.findIndex(el => el.localName.toLowerCase() === 've-navbar')
  if (stickyNavBarIdx < 0) {
    let headerIdx = stickyElems.findIndex(el => el.localName.toLowerCase() === 've-header')
    if (headerIdx >= 0) {
      let stickyNavBar = stickyElems[headerIdx].shadowRoot.querySelector('ve-navbar.sticky')
      if (stickyNavBar) {
        stickyElems[headerIdx] = stickyNavBar
        stickyNavBarIdx = headerIdx
      }
    }
  }
  let main = document.querySelector('main')
  if (main) main.style.paddingBottom = '75vh'
  stickyElems.forEach(el => setTop(el))
  return stickyElems
}

function activeRegionOffset() {
  let stickyNavBar = stickyElems.find(el => el.localName.toLowerCase() === 've-navbar')
  let offset = stickyNavBar ? stickyNavBar.getBoundingClientRect().top : 0
  stickyElems.forEach(el => {
    let bcr = el.getBoundingClientRect()
    let col = bcr.x < bcr.width ? 0 : 1
    if (col === 0 && bcr.top === offset) {
      let computedHeightStyle = window.getComputedStyle(el).height
      if (computedHeightStyle.length >= 3 && computedHeightStyle.slice(-2) === 'px') {
        offset += parseInt(window.getComputedStyle(el).height.slice(0,-2))
      }
    }
  })
  return offset
}

function setTop(el) {
  if (el.localName.toLowerCase() === 'section') {
    let stickyNavBar = stickyElems.find(el => el.localName.toLowerCase() === 've-navbar')
    // let offset = stickyNavBar ? stickyNavBar.getBoundingClientRect().top : 0
    let offset = stickyNavBar ? stickyNavBar.clientHeight : 0
    el.style.top = `${offset}px`
  }
}

let stickyElems = []
const mutationObserver = new MutationObserver(() => stickyElems = findStickyElems())
mutationObserver.observe(document, { childList: true, subtree: true })

let targets = {}
let active

let offset = 0

const intersectionObserver = new IntersectionObserver (
  (entries, observer) => {
    offset = activeRegionOffset(stickyElems)
    // console.log(offset)
    entries.forEach(entry => targets[domPath(entry.target)] = entry)
    let intersecting = Object.values(targets)
      .filter(entry => entry.isIntersecting)
      .filter(entry => entry.target.getBoundingClientRect().y >= offset)
      .sort((a,b) => a.target.getBoundingClientRect().y > b.target.getBoundingClientRect().y ? 1 : -1)
    let selected = (intersecting.find(entry => entry.intersectionRatio === 1) || intersecting[0])
    if (selected) {
      selected = selected.target
      if (Array.from(selected.classList).indexOf('active') < 0) {
        if (active) active.classList.remove('active')
        selected.classList.add('active')
        active = selected
      }
    }
  },
  { root: null, threshold: [0, 0.25, 0.5, 0.75, 1], rootMargin: `-${offset}px 0px 0px 0px` }
)
Array.from(document.querySelectorAll('p')).forEach(el => intersectionObserver.observe(el))
*/

document.body.classList.remove('hidden')
document.body.classList.add('visible')

// Google Analytics
window.dataLayer = window.dataLayer || []
function gtag(){dataLayer.push(arguments)}
gtag('js', new Date())
gtag('config', 'G-DRHNQSMN5Y')
