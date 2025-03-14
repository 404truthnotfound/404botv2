// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/math/SafeMath.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

// Interfaces
interface ILendingPoolAddressesProvider {
    function getLendingPool() external view returns (address);
}

interface ILendingPool {
    function flashLoan(
        address receiverAddress,
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata modes,
        address onBehalfOf,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IUniswapV2Router02 {
    function getAmountsOut(uint amountIn, address[] memory path) external view returns (uint[] memory amounts);
    function getAmountsIn(uint amountOut, address[] memory path) external view returns (uint[] memory amounts);
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
}

/**
 * @title OptimizedFlashLoanArbitrage
 * @dev A contract for flash loan arbitrage between different DEXes with optimized gas usage
 */
contract OptimizedFlashLoanArbitrage is Ownable, ReentrancyGuard {
    using SafeMath for uint256;
    using SafeERC20 for IERC20;

    // Constants
    address public immutable aaveLendingPool;
    address public immutable uniswapRouter;
    address public immutable sushiswapRouter;
    
    // Common base tokens (stored as constants to save gas)
    address public constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address public constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    address public constant USDT = 0xdAC17F958D2ee523a2206206994597C13D831ec7;
    address public constant DAI = 0x6B175474E89094C44Da98b954EedeAC495271d0F;
    address public constant WBTC = 0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599;

    // Configurable parameters
    uint256 public slippageTolerance = 200; // 2% (in basis points)
    uint256 public minProfit = 0; // Minimum profit threshold
    uint256 public constant MAX_DEADLINE = 1200; // 20 minutes in seconds

    // Events
    event ProfitGenerated(address indexed tokenBorrowed, uint256 amount, uint256 profit);
    event ArbitrageFailed(address indexed token, string reason);
    event SwapExecuted(address indexed router, address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut);
    event SlippageToleranceUpdated(uint256 newTolerance);
    event MinProfitUpdated(uint256 newMinProfit);

    /**
     * @dev Constructor
     * @param _aaveLendingPool Aave lending pool address
     * @param _uniswapRouter Uniswap V2 router address
     * @param _sushiswapRouter SushiSwap router address
     */
    constructor(
        address _aaveLendingPool,
        address _uniswapRouter,
        address _sushiswapRouter
    ) {
        require(_aaveLendingPool != address(0), "Invalid Aave lending pool address");
        require(_uniswapRouter != address(0), "Invalid Uniswap router address");
        require(_sushiswapRouter != address(0), "Invalid SushiSwap router address");

        aaveLendingPool = _aaveLendingPool;
        uniswapRouter = _uniswapRouter;
        sushiswapRouter = _sushiswapRouter;
    }

    /**
     * @dev Executes a flash loan for arbitrage
     * @param token Token to borrow
     * @param amount Amount to borrow
     */
    function executeFlashLoan(address token, uint256 amount) external onlyOwner {
        require(token != address(0), "Invalid token address");
        require(amount > 0, "Amount must be greater than 0");

        address[] memory assets = new address[](1);
        assets[0] = token;

        uint256[] memory amounts = new uint256[](1);
        amounts[0] = amount;

        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // 0 = no debt, 1 = stable, 2 = variable

        // Empty params means default behavior - check prices on both DEXes and execute the profitable arbitrage
        bytes memory params = abi.encode(address(0), address(0), new address[](0));

        // Execute flash loan
        ILendingPool(aaveLendingPool).flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            params,
            0 // referral code
        );
    }

    /**
     * @dev Executes a flash loan with a specific trading path
     * @param token Token to borrow
     * @param amount Amount to borrow
     * @param sourceRouter Router to buy from
     * @param targetRouter Router to sell to
     * @param path Token path for swaps
     */
    function executeFlashLoanWithPath(
        address token,
        uint256 amount,
        address sourceRouter,
        address targetRouter,
        address[] calldata path
    ) external onlyOwner {
        require(token != address(0), "Invalid token address");
        require(amount > 0, "Amount must be greater than 0");
        require(sourceRouter != address(0), "Invalid source router");
        require(targetRouter != address(0), "Invalid target router");
        require(path.length >= 2, "Path must have at least 2 tokens");
        require(path[0] == token, "Path must start with borrowed token");
        require(path[path.length - 1] == token, "Path must end with borrowed token");

        address[] memory assets = new address[](1);
        assets[0] = token;

        uint256[] memory amounts = new uint256[](1);
        amounts[0] = amount;

        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // 0 = no debt, 1 = stable, 2 = variable

        // Encode params for specific router and path
        bytes memory params = abi.encode(sourceRouter, targetRouter, path);

        // Execute flash loan
        ILendingPool(aaveLendingPool).flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            params,
            0 // referral code
        );
    }

    /**
     * @dev Flash loan callback function
     * @param assets Asset addresses
     * @param amounts Borrowed amounts
     * @param premiums Fees that need to be paid
     * @param initiator Flash loan initiator
     * @param params Encoded parameters
     * @return Whether operation was successful
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external nonReentrant returns (bool) {
        require(msg.sender == aaveLendingPool, "Caller must be Aave lending pool");
        require(initiator == address(this), "Initiator must be this contract");

        // Extract parameters
        (address sourceRouter, address targetRouter, address[] memory path) = abi.decode(
            params,
            (address, address, address[])
        );

        // Get borrowed token and amount
        address token = assets[0];
        uint256 borrowedAmount = amounts[0];
        uint256 fee = premiums[0];
        uint256 totalRepayment = borrowedAmount.add(fee);

        // If specific path is provided, use that
        if (sourceRouter != address(0) && targetRouter != address(0) && path.length >= 2) {
            executePredefinedArbitrage(token, borrowedAmount, sourceRouter, targetRouter, path, totalRepayment);
        } else {
            // Otherwise, dynamically find the best arbitrage opportunity
            executeDynamicArbitrage(token, borrowedAmount, totalRepayment);
        }

        // Approve the LendingPool to pull the owed amount
        IERC20(token).safeApprove(aaveLendingPool, totalRepayment);

        return true;
    }

    /**
     * @dev Execute arbitrage with predefined parameters
     */
    function executePredefinedArbitrage(
        address token,
        uint256 borrowedAmount,
        address sourceRouter,
        address targetRouter,
        address[] memory path,
        uint256 totalRepayment
    ) internal {
        // Approve source router to spend borrowed token
        IERC20(token).safeApprove(sourceRouter, borrowedAmount);

        // Determine minimum amount out to prevent sandwich attacks
        uint256[] memory amountsOut = IUniswapV2Router02(sourceRouter).getAmountsOut(borrowedAmount, path);

        // Calculate slippage-adjusted minimum output
        uint256 amountOutMin = amountsOut[1].mul(10000 - slippageTolerance).div(10000);

        // Execute first swap
        address[] memory firstPairPath = getFirstPairPath(path);
        uint256[] memory swapResult = IUniswapV2Router02(sourceRouter).swapExactTokensForTokens(
            borrowedAmount,
            amountOutMin,
            firstPairPath,
            address(this),
            block.timestamp + MAX_DEADLINE
        );

        // Emit swap event
        emit SwapExecuted(sourceRouter, firstPairPath[0], firstPairPath[1], borrowedAmount, swapResult[1]);

        // Get intermediate token and amount
        address intermediateToken = path[1];
        uint256 intermediateAmount = IERC20(intermediateToken).balanceOf(address(this));

        // Approve target router for the intermediate token
        IERC20(intermediateToken).safeApprove(targetRouter, intermediateAmount);

        // Get min amount out for second swap
        address[] memory reversePath = getReversePath(path);
        uint256[] memory amountsOutReverse = IUniswapV2Router02(targetRouter).getAmountsOut(
            intermediateAmount,
            reversePath
        );
        uint256 amountOutMinReverse = amountsOutReverse[1].mul(10000 - slippageTolerance).div(10000);

        // Execute second swap
        uint256[] memory reverseSwapResult = IUniswapV2Router02(targetRouter).swapExactTokensForTokens(
            intermediateAmount,
            amountOutMinReverse,
            reversePath,
            address(this),
            block.timestamp + MAX_DEADLINE
        );

        // Emit swap event
        emit SwapExecuted(targetRouter, reversePath[0], reversePath[1], intermediateAmount, reverseSwapResult[1]);

        // Check profit
        uint256 finalBalance = IERC20(token).balanceOf(address(this));
        require(finalBalance >= totalRepayment, "Not enough funds to repay flash loan");

        // Calculate profit
        uint256 profit = finalBalance.sub(totalRepayment);
        require(profit >= minProfit, "Profit below minimum threshold");
        
        emit ProfitGenerated(token, borrowedAmount, profit);
    }

    /**
     * @dev Execute dynamic arbitrage by checking multiple DEXes
     */
    function executeDynamicArbitrage(
        address token,
        uint256 borrowedAmount,
        uint256 totalRepayment
    ) internal {
        // Build potential paths
        address[] memory dexRouters = new address[](2);
        dexRouters[0] = uniswapRouter;
        dexRouters[1] = sushiswapRouter;

        // Get common tokens for intermediate swaps
        address[] memory intermediateTokens = getCommonBaseTokens();

        uint256 bestProfit = 0;
        address bestSourceRouter;
        address bestTargetRouter;
        address bestIntermediateToken;

        // Find the best arbitrage opportunity across all pairs
        for (uint i = 0; i < intermediateTokens.length; i++) {
            address intermediateToken = intermediateTokens[i];
            
            // Skip if intermediate token is the same as token
            if (intermediateToken == token) continue;
            
            for (uint j = 0; j < dexRouters.length; j++) {
                address sourceRouter = dexRouters[j];
                
                for (uint k = 0; k < dexRouters.length; k++) {
                    if (j == k) continue; // Skip same DEX

                    address targetRouter = dexRouters[k];

                    // Calculate potential profit
                    uint256 profit = simulateArbitrage(token, borrowedAmount, sourceRouter, targetRouter, intermediateToken);

                    if (profit > bestProfit) {
                        bestProfit = profit;
                        bestSourceRouter = sourceRouter;
                        bestTargetRouter = targetRouter;
                        bestIntermediateToken = intermediateToken;
                    }
                }
            }
        }

        // Execute the best arbitrage if profitable
        if (bestProfit > minProfit && bestSourceRouter != address(0) && bestTargetRouter != address(0)) {
            // Create path
            address[] memory path = new address[](3);
            path[0] = token;
            path[1] = bestIntermediateToken;
            path[2] = token;

            executePredefinedArbitrage(
                token,
                borrowedAmount,
                bestSourceRouter,
                bestTargetRouter,
                path,
                totalRepayment
            );
        } else {
            // No profitable arbitrage found
            emit ArbitrageFailed(token, "No profitable arbitrage opportunity found");
            revert("No profitable arbitrage opportunity found");
        }
    }

    /**
     * @dev Simulate arbitrage to find potential profit
     */
    function simulateArbitrage(
        address token,
        uint256 amount,
        address sourceRouter,
        address targetRouter,
        address intermediateToken
    ) internal view returns (uint256) {
        // Create paths
        address[] memory path = new address[](2);
        path[0] = token;
        path[1] = intermediateToken;

        address[] memory reversePath = new address[](2);
        reversePath[0] = intermediateToken;
        reversePath[1] = token;

        try IUniswapV2Router02(sourceRouter).getAmountsOut(amount, path) returns (uint256[] memory amountsOut) {
            uint256 intermediateAmount = amountsOut[1];

            try IUniswapV2Router02(targetRouter).getAmountsOut(intermediateAmount, reversePath) returns (uint256[] memory reverseAmountsOut) {
                uint256 finalAmount = reverseAmountsOut[1];

                if (finalAmount > amount) {
                    return finalAmount - amount;
                }
            } catch {
                // Path not available on target router
            }
        } catch {
            // Path not available on source router
        }

        return 0; // No profit
    }

    /**
     * @dev Get first pair path for swap
     */
    function getFirstPairPath(address[] memory fullPath) internal pure returns (address[] memory) {
        require(fullPath.length >= 2, "Path too short");

        address[] memory path = new address[](2);
        path[0] = fullPath[0];
        path[1] = fullPath[1];

        return path;
    }

    /**
     * @dev Get reverse path for second swap
     */
    function getReversePath(address[] memory fullPath) internal pure returns (address[] memory) {
        require(fullPath.length >= 3, "Path too short");

        address[] memory path = new address[](2);
        path[0] = fullPath[1];  // Intermediate token
        path[1] = fullPath[2];  // Final token (same as initial token)

        return path;
    }

    /**
     * @dev Get common base tokens for trading
     */
    function getCommonBaseTokens() internal pure returns (address[] memory) {
        // These addresses are for mainnet
        address[] memory tokens = new address[](5);
        tokens[0] = WETH;
        tokens[1] = USDC;
        tokens[2] = USDT;
        tokens[3] = DAI;
        tokens[4] = WBTC;

        return tokens;
    }

    /**
     * @dev Update slippage tolerance
     * @param _slippageTolerance New slippage tolerance in basis points (e.g., 200 = 2%)
     */
    function updateSlippageTolerance(uint256 _slippageTolerance) external onlyOwner {
        require(_slippageTolerance <= 1000, "Slippage tolerance too high"); // Max 10%
        slippageTolerance = _slippageTolerance;
        emit SlippageToleranceUpdated(_slippageTolerance);
    }

    /**
     * @dev Update minimum profit threshold
     * @param _minProfit New minimum profit threshold
     */
    function updateMinProfit(uint256 _minProfit) external onlyOwner {
        minProfit = _minProfit;
        emit MinProfitUpdated(_minProfit);
    }

    /**
     * @dev Withdraw tokens from the contract
     * @param token The token to withdraw
     */
    function withdrawToken(address token) external onlyOwner {
        IERC20 tokenInstance = IERC20(token);
        uint256 balance = tokenInstance.balanceOf(address(this));
        require(balance > 0, "No tokens to withdraw");

        tokenInstance.safeTransfer(owner(), balance);
    }

    /**
     * @dev Withdraw ETH from the contract
     */
    function withdrawETH() external onlyOwner {
        uint256 balance = address(this).balance;
        require(balance > 0, "No ETH to withdraw");
        
        (bool success, ) = payable(owner()).call{value: balance}("");
        require(success, "ETH transfer failed");
    }

    // Function to receive ETH
    receive() external payable {}
}
